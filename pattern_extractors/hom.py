import os
import argparse

from ghc.homomorphism import get_hom_profile
from ghc.utils.data import load_precompute, save_precompute,\
                           precompute_patterns_file_handle,\
                           load_data_for_json, hom2json, save_json, load_precompute_patterns



def compute_hom(passed_args=None):

    hom_types = get_hom_profile(None)

    #### Parse arguments
    parser = argparse.ArgumentParser()
    parser.add_argument('--pattern_count', type=int, default=50)
    parser.add_argument('--run_id', type=str, default=0)
    parser.add_argument('--hom_size', type=int, default=6)
    parser.add_argument('--max_treewidth', type=int, default=6)
    parser.add_argument('--data', default='MUTAG')
    parser.add_argument('--hom_type', type=str, choices=hom_types)
    parser.add_argument('--dloc', type=str, default="./data")
    parser.add_argument('--oloc', type=str, default="./data")

    # arguments for compatibility reasons which are ignored
    parser.add_argument('--seed', type=int, default=0)
    parser.add_argument('--epochs', type=int, default=5000)
    parser.add_argument('--bs', type=int, default=32)
    parser.add_argument('--lr', type=float, default=0.001)
    parser.add_argument('--wd', type=float, default=0.00005)
    parser.add_argument('--hids', type=int, nargs='+', default=[64, 64, 64])
    parser.add_argument('--dropout', type=float, default=0.5)
    parser.add_argument('--patience', type=int, default=500)
    parser.add_argument('--cuda', action="store_true", default=False)
    parser.add_argument('--verbose', action="store_true", default=False)
    parser.add_argument('--gpu_id', type=int, default=0)
    parser.add_argument("--log_period", type=int, default=200)
    parser.add_argument("--grid_search", action="store_true", default=False)


    # Load partial args instead of command line args (if they are given)
    if passed_args is not None:
        # Transform dict to list of args
        list_args = []
        for key,value in passed_args.items():
            # The case with "" happens if we want to pass an argument that has no parameter
            list_args += [key, str(value)]

        args = parser.parse_args(list_args)
    else:
        args = parser.parse_args()

    
    
    if args.hom_size == -1:
        args.hom_size = 'max' # use maximum graph size in database
    
    #### Setup checkpoints and precompute
    os.makedirs(args.oloc, exist_ok=True)
    
    #### Load data and compute homomorphism
    graphs, _, y, metas = load_data_for_json(args.data.upper(), args.dloc)
    hom_func = get_hom_profile(args.hom_type)
    try:
        homX = load_precompute(args.data.upper(),
                                args.hom_type,
                                args.hom_size,
                                args.pattern_count,
                                args.run_id,
                                args.oloc)
        print(f'({args.data.upper()},{args.hom_type},{args.hom_size},{args.pattern_count},{args.run_id},{args.oloc}) loads')
        

    except FileNotFoundError:
        # changed it to batch computation to not recompute the patterns each time
        with precompute_patterns_file_handle(args.data.upper(), args.hom_type, args.hom_size, args.pattern_count, args.run_id, args.oloc) as f:
            homX = hom_func(graphs, 
                            size=args.hom_size, 
                            max_treewidth=args.max_treewidth,
                            density=False, 
                            seed=args.seed, 
                            pattern_count=args.pattern_count, 
                            pattern_file=f,
                            )
        save_precompute(homX, args.data.upper(), args.hom_type, args.hom_size, args.pattern_count, args.run_id, args.oloc)

        metas = hom2json(metas, homX, y)
        try:
            pattern_sizes = [len(p.nodes) for p in load_precompute_patterns(args.data.upper(), args.hom_type, args.hom_size, args.pattern_count, args.run_id, args.oloc)]
        except EOFError:
            ## TODO careful: this is hacky and supposed to work for for WL patterns, that don't have any size we want to compute
            pattern_sizes = [args.pattern_count for _ in range(homX.shape[1])]

        metas = {'pattern_sizes': pattern_sizes, 'data': metas}
        save_json(metas, args.data.upper(), args.hom_type, args.hom_size, args.pattern_count, args.run_id, args.oloc)
    
if __name__ == "__main__":
    compute_hom(passed_args=None)
