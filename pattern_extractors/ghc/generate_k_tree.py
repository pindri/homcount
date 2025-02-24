import networkx as nx
import random
import itertools

from ghc.utils.HomSubio import HomSub, PACE_graph_format
from ghc.utils.fast_weisfeiler_lehman import *
from ghc.utils.converter import filter_overflow
import numpy as np
import scipy.spatial.distance as sp
from tqdm import tqdm
import pickle


def random_ktree_decomposition(N, k, seed=None):
    '''Sample a random ktree on N vertices.
    
    To this end, draw a random tree that defines the topology of the 
    tree decomposition and then randomly create bags for a full, nice 
    tree decomposition.
    '''

    if k > N - 1:
        raise ValueError(f'k(={k})+1 cannot be larger than N(={N})')

    # sample a random tree for the tree decomposition
    T = nx.generators.random_labeled_tree(N-k, seed=seed)
    bfs = nx.bfs_edges(T, 0)

    rnd = random.seed(seed)

    # construct bags of a k-tree. The first bag consists of the first k+1 vertices and is fully connected
    bags = [None for _ in range(N-k)]
    bags[0] = [v for v in range(k+1)] # I assume shuffling is not necessary, as T is random
    edges = [e for e in itertools.combinations(bags[0], 2)]

    candidates = [v for v in range(k+1, N)]

    PACE_tdstring = f's td {N-k} {k+1} {N}\n'
    PACE_bagstrings = ['' for _ in range(N-k)]
    PACE_bagstrings[0] = 'b 1 ' + ' '.join([str(v + 1) for v in bags[0]])

    PACE_tdedges = ''

    for i, e in enumerate(bfs):
        bag = bags[e[0]].copy()
        deleted_vertex = bag.pop(random.randint(0, k-1))
        new_vertex = candidates[i]
        for v in bag:
            edges.append((v, new_vertex))
        bag.append(new_vertex)
        bags[e[1]] = bag

        PACE_bagstrings[e[1]] = f'b {e[1] + 1} ' + ' '.join([str(v + 1) for v in bag]) 
        PACE_tdedges += f'{min(e[0], e[1]) + 1} {max(e[0], e[1]) + 1}\n'

    PACE_tdstring += '\n'.join(PACE_bagstrings) + '\n' + PACE_tdedges    
    tree_decomposition = (T, bags)

    return edges, tree_decomposition, PACE_tdstring


def erdos_filter(edges, p=0.9, seed=None):
    '''Delete edges from edge list i.i.d. with probability 1-p.
    I.e., keep any edge with probability p'''

    random.seed(seed)

    filtered_edges = list()
    for e in edges:
        if random.random() < p:
            filtered_edges.append(e)

    return filtered_edges


def connected_filter(P):
    '''Return the list of connected components, as networkx graphs'''

    S = [P.subgraph(c).copy() for c in nx.connected_components(P)]
    return S


def partial_ktree_sample(N, k, p, seed=None):
    '''Returns a list of networkx graphs that are the connected components of a 
    partial ktree that was obtained by deleting edges with probability p from a 
    random k tree on N vertices. '''

    edges, td, string = random_ktree_decomposition(N, k, seed=seed)
    filtered_edges = erdos_filter(edges, p=p, seed=seed)
    filtered_graph = nx.empty_graph(n=N)
    filtered_graph.add_edges_from(filtered_edges)
    # connected_components = connected_filter(filtered_graph)

    return filtered_graph, string


def Nk_strategy_geom(max_size, pattern_count, p='by_max'):

    if p == 'by_max':
        p = 1. - 1. / max_size

    # draw sizes from uniform distribution
    sizes = np.random.randint(2, max_size+1, size=pattern_count)

    # draw treewidths from geometric distribution, but bounded by size - 1
    treewidths = np.random.default_rng().geometric(p=p, size=pattern_count)
    treewidths = np.where(treewidths<sizes-1, treewidths, sizes - 1)

    return sizes, treewidths


def Nk_strategy_poisson(max_size, pattern_count, lam='by_max'):

    if lam == 'by_max':
        lam = (1. + 3 * np.log(max_size)) / max_size

    # draw sizes from uniform distribution
    sizes = np.random.randint(2, max_size+1, size=pattern_count)

    # draw treewidths from geometric distribution, but bounded by size - 1
    treewidths = 1 + np.random.default_rng().poisson(lam=lam, size=pattern_count)
    treewidths = np.where(treewidths<sizes-1, treewidths, sizes - 1)

    return sizes, treewidths


def Nk_strategy_fiddly(max_size, pattern_count, lam='by_max', min_size=0, max_treewidth=10):
    '''This is the proposed samping strategy for in expectation polynomial run time that is proposed in the paper'''

    assert max_size-1>=max_treewidth, "The maximum treewidth should be at most max_size-1"

    # we want to be polynomial time in expectation
    if lam == 'by_max':
        lam = (1. + np.log(max_size)) / max_size

    # we want the patterns to be at most max_size with probability .99
    p = 1 - np.power(0.01, 1. / (max_size - min_size))

    # draw sizes from geometric distribution
    sizes = np.random.default_rng().geometric(p=p, size=pattern_count) + min_size

    # draw treewidths from poisson distribution, but bounded by size - 1
    # draw treewidths from poisson distribution, but bounded by max_treewidth
    treewidths = np.random.randint(1, 4, size=pattern_count) + np.random.default_rng().poisson(lam=lam, size=pattern_count)
    # treewidths = np.where(treewidths<sizes-1, treewidths, sizes - 1)
    treewidths = np.where(treewidths<max_treewidth, treewidths, max_treewidth)

    return sizes, treewidths


# this is currently our default selection strategy for pattern sizes and treewidths
Nk_strategy = Nk_strategy_fiddly


def get_small_patterns():
    singleton, td_singleton = partial_ktree_sample(N=1, k=0, p=1)
    edge, td_edge = partial_ktree_sample(N=2, k=1, p=1)
    path, td_path = partial_ktree_sample(N=3, k=1, p=1)
    tria, td_tria = partial_ktree_sample(N=3, k=2, p=1)
    return [singleton, edge, path, tria], [td_singleton, td_edge, td_path, td_tria]


def get_pattern_list(size, pattern_count, min_size=0, max_treewidth=10):
    
    partial_ktree_edge_keeping_p = 0.9
    
    # TODO: handling possibly disconnected patterns, now. 
    # this function can be simplified
    kt_list = list()
    td_list = list()
    while len(kt_list) < pattern_count:
        
        sizes, treewidths = Nk_strategy(size, 1, 'by_max', min_size=min_size, max_treewidth=max_treewidth)
        pattern, td = partial_ktree_sample(N=sizes[0], k=treewidths[0], p=partial_ktree_edge_keeping_p)

        kt_list += [pattern]
        td_list += [td]
        
    kt_list = kt_list[:pattern_count] # the above might result in more than pattern_count patterns
    td_list = td_list[:pattern_count]
    return kt_list, td_list


def min_kernel(graphs, size='max', density=False, seed=8, pattern_count=50, early_stopping=10, metadata=None, pattern_file=None, **kwargs):
    patterns = random_ktree_profile(graphs, size=size, density=density, seed=seed, pattern_count=pattern_count, early_stopping=early_stopping, metadata=metadata, pattern_file=pattern_file,
                                # this is what we really fix for the min_kernel
                                min_embedding=True, add_small_patterns=True, **kwargs)
    return patterns


def full_kernel(graphs, size='max', density=False, seed=8, pattern_count=50, early_stopping=10, metadata=None, pattern_file=None, **kwargs):
    patterns = random_ktree_profile(graphs, size=size, density=density, seed=seed, pattern_count=pattern_count, early_stopping=early_stopping, metadata=metadata, pattern_file=pattern_file,
                                # this is what we really fix for the full_kernel
                                min_embedding=False, add_small_patterns=True, **kwargs)
    return patterns


# def filter_overflow(patterns):
#     minval = np.min(patterns, axis=0)
#     patterns = patterns[:, minval >= 0]
#     if patterns.shape[1] > 0:
#         return patterns
#     else: 
#         # if nothing worked, return zeros
#         return np.zeros([patterns.shape[0], 1])


def random_ktree_profile(graphs, size='max', max_treewidth=10, density=False, seed=8, pattern_count=50, early_stopping=10, metadata=None, min_embedding=True, add_small_patterns=False, pattern_file=None, filter_and_retry=True, **kwargs):
    '''

    Parameters:
        - add_small_patterns: If true, the first four patterns will be the singleton, the edge, the wedge, and the triangle. Further samples will have size at least four.
    '''

    print("Max treewidth:")
    print(max_treewidth)

    if size == 'max':
        size = max([len(g.nodes) for g in graphs])
    
    if size == 'half_max':
        size = max([len(g.nodes) for g in graphs]) / 2

    

    if add_small_patterns:
        # the 4 patterns of size 1-3 are added deterministically and do not need to be sampled
        # hence we reduce the pattern count and increase the min pattern size
        min_pattern_size = 4
        kt_list, td_list = get_pattern_list(size, pattern_count=pattern_count - 4, min_size=min_pattern_size, max_treewidth=max_treewidth)
        kt_small, td_small = get_small_patterns()
        kt_list = kt_small + kt_list
        td_list = td_small + td_list
    else:
        # just sample the requested number of patterns
        min_pattern_size = 0
        kt_list, td_list = get_pattern_list(size, pattern_count=pattern_count - 4, min_size=min_pattern_size, max_treewidth=max_treewidth)

    # compute homomorphism counts
    embeddings = HomSub(pattern_list=kt_list, graph_list=graphs, td_list=td_list, min_embedding=min_embedding)

    # here, we remove patterns for which the homcount overflowed and resample new patterns if necessary
    # TODO: note that this process might take very long to terminate if we frequently draw patterns which overflow the homcounts
    if filter_and_retry:
        print("OVERFLOE")
        embeddings, kt_list = filter_overflow(embeddings, kt_list)
        while embeddings.shape[1] < pattern_count:
            kt_tmp, td_tmp = get_pattern_list(size, pattern_count=pattern_count - embeddings.shape[1], min_size=min_pattern_size, max_treewidth=max_treewidth)
            embeddings_tmp = HomSub(pattern_list=kt_tmp, graph_list=graphs, td_list=td_tmp, min_embedding=min_embedding)
            embeddings_tmp, kt_tmp = filter_overflow(embeddings, kt_tmp)

            # append new filtered patterns
            kt_list = kt_list + kt_tmp
            embeddings = np.hstack([embeddings, embeddings])

    # store patterns and return output
    if pattern_file is not None:
        pickle.dump(kt_list, pattern_file)
    return embeddings



def random_ktree_profile_relative_to_wl(graphs, size='max', density=False, seed=8, pattern_count=50, early_stopping=10, metadata=None, min_embedding=True, add_small_patterns=False, pattern_file=None, **kwargs):
    '''

    Parameters:
        - add_small_patterns: If true, the first four patterns will be the singleton, the edge, the wedge, and the triangle. Further samples will have size at least four.
    '''

    if size == 'max':
        size = max([len(g.nodes) for g in graphs])
    
    if size == 'half_max':
        size = max([len(g.nodes) for g in graphs]) / 2

    if add_small_patterns:
        min_pattern_size = 4
    else:
        min_pattern_size = 0


    if pattern_count > -1:
        # return the requested number of patterns
        kt_list, td_list = get_pattern_list(size, pattern_count, min_size=min_pattern_size)

        if add_small_patterns:
            kt_small, td_small = get_small_patterns()
            kt_list = kt_small + kt_list
            td_list = td_small + td_list

        if pattern_file is not None:
            pickle.dump(kt_list, pattern_file)

        return HomSub(pattern_list=kt_list, graph_list=graphs, td_list=td_list, min_embedding=min_embedding)
    
    else:
        # adjust pattern count wrt. expressive power on input data. the negative number gives the n_iter of wl
        pattern_list = list()

        if metadata is not None:
            # we know the training split 
            # we want to be not transductive, but truly inductive
            traingraphs = list()
            train_idx = list()
            for graph, meta in zip(graphs, metadata):
                if meta['split'] == 'train':
                    traingraphs.append(graph)
                    train_idx.append(meta['idx'])

            wl_nodelabels = homsub_format_wl_nodelabels(traingraphs, vertex_features=None, n_iter=-pattern_count)
            wl_representations = np.array([np.sum(g, axis=0) for g in wl_nodelabels])
        else:
            # use full dataset for wl adjustment
            wl_nodelabels = homsub_format_wl_nodelabels(graphs, vertex_features=None, n_iter=-pattern_count)
            wl_representations = np.array([np.sum(g, axis=0) for g in wl_nodelabels])

        if add_small_patterns:
            kt_list, td_list = get_small_patterns()
            pattern_list += kt_list
            hom_representations = HomSub(pattern_list=kt_list, graph_list=graphs, td_list=td_list, min_embedding=min_embedding)
            if metadata is not None:
                hom_comp_reps = hom_representations[train_idx, :]
            else:
                hom_comp_reps = hom_representations
            comparison = compare_equivalence_classes(filter_overflow(hom_comp_reps), wl_representations)
        else:
            hom_representations = None
            comparison = -1

        stop_step = 0
        while comparison < 0:

            kt_list, td_list = get_pattern_list(size, 1, min_size=min_pattern_size)
            pattern_list += kt_list
            new_emb = HomSub(pattern_list=kt_list, graph_list=graphs, td_list=td_list, min_embedding=min_embedding)
            if hom_representations is None:
                hom_representations = new_emb
            else:
                hom_representations = np.hstack([hom_representations, new_emb])

            if metadata is not None:
                hom_comp_reps = hom_representations[train_idx, :]
            else:
                hom_comp_reps = hom_representations

            comparison_new = compare_equivalence_classes(filter_overflow(hom_comp_reps), wl_representations)
            if comparison_new <= comparison:
                stop_step += 1
            else:
                stop_step = 0
            
            comparison = comparison_new
            if stop_step >= early_stopping:
                break

        print(f'NOTE hom representations have shape {hom_representations.shape} to be as powerful as wl with n_iter={-pattern_count} (shape={wl_representations.shape}).\n  wl has {np.unique(wl_representations, axis=0).shape[0]} unique reps, hom has {np.unique(hom_representations, axis=0).shape[0]} unique reps')
        if pattern_file is not None:
            pickle.dump(pattern_list, pattern_file)
        return hom_representations
