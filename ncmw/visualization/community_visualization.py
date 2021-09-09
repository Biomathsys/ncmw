import matplotlib.pyplot as plt
import numpy as np
import matplotlib

from ncmw.community import (
    compute_community_interaction_graph,
    community_weight_posterior,
    compute_pairwise_growth_relation_per_weight,
    compute_species_interaction_weights,
)
from utils import get_reference_network_weights
from networkx.drawing.layout import circular_layout, bipartite_layout
import networkx as nx
import torch
from copy import deepcopy


def plot_reference_interaction(interaction_cutoff=0, cmap="viridis"):
    nodes, weights = get_reference_network_weights()
    N = len(weights)
    G = nx.DiGraph()
    G.add_nodes_from(nodes)
    cmap = matplotlib.cm.get_cmap(cmap)
    cmap2 = matplotlib.cm.get_cmap("jet_r")
    edge_color = []
    colors = [cmap(i / len(nodes)) for i in range(len(nodes))]
    for i in range(N):
        for j in range(N):
            if i != j and np.abs(weights[i, j]) > interaction_cutoff:
                n1 = nodes[i]
                n2 = nodes[j]
                G.add_edge(n1, n2, weight=weights[i, j])
                edge_color.append(cmap2((weights[i, j])))

    fig = plt.figure(figsize=(N, N - 2))
    pos = circular_layout(G)
    nx.draw(
        G,
        with_labels=True,
        pos=pos,
        node_size=1000,
        font_size=8,
        node_color=colors,
        edge_color=edge_color,
        width=3,
        connectionstyle="arc3, rad = 0.1",
    )
    cbar = fig.colorbar(
        matplotlib.cm.ScalarMappable(matplotlib.colors.Normalize(-1, 1), cmap=cmap2)
    )
    cbar.set_label("Interaction (Red=harmful, Blue=Benefitial)", rotation=270)
    cbar.set_ticks([-1, 0, 1])

    return fig


def plot_species_interaction(
    model, df, names: dict = dict(), cmap="viridis", interaction_cutoff=0.0
):
    G = nx.DiGraph()
    weights = compute_species_interaction_weights(model, df)
    names = []
    for m in model.models:
        if m.id in names:
            names.append(names[m.id])
        else:
            names.append(m.id.split("_")[0])
    cmap = matplotlib.cm.get_cmap(cmap)
    cmap2 = matplotlib.cm.get_cmap("jet_r")
    G.add_nodes_from(names)

    edge_color = []
    colors = [cmap(i / len(names)) for i in range(len(names))]
    for i in range(len(model.models)):
        for j in range(len(model.models)):
            if i != j and np.abs(weights[i, j]) > interaction_cutoff:
                n1 = names[i]
                n2 = names[j]
                G.add_edge(n1, n2, weight=weights[i, j])
                edge_color.append(cmap2((weights[i, j] + 1) / 2))

    fig = plt.figure(figsize=(len(model.models) * 2, 2 * len(model.models) - 2))
    pos = circular_layout(G)
    nx.draw(
        G,
        with_labels=True,
        pos=pos,
        node_size=1000,
        font_size=8,
        node_color=colors,
        edge_color=edge_color,
        width=3,
        connectionstyle="arc3, rad = 0.1",
    )
    cbar = fig.colorbar(
        matplotlib.cm.ScalarMappable(matplotlib.colors.Normalize(-1, 1), cmap=cmap2)
    )
    cbar.set_label("Interaction (Red=harmful, Blue=Benefitial)", rotation=270)
    cbar.set_ticks([-1, 0, 1])

    return fig


def plot_posterior_samples_for_observations(model, observations):
    """This method plots posterior samples p(w|x) where x is the observed biomass
    values. For this purpuse we assume a Dirichlet prior on weights. This also gurantees
    that the weights sum to one.



        Args:
            model: Community Models
            observations: List of observed biomass values.

        Returns:
            list : A list of figures for each observation.

    """
    posterior = community_weight_posterior(model)
    figs = []
    for x_o in observations:
        x_o = torch.tensor(x_o).float()
        posterior.set_default_x(x_o)
        posterior.train(loss="forward_kl", warm_up_rounds=100)
        samples = posterior.sample((10000,))
        fig, axes = sbi.analysis.pairplot(
            samples, labels=["Weights: " + m.id.split("_")[0] for m in model.models]
        )
        fig.suptitle(
            f"Observed Growth: {[np.round(float(x),4) for x in x_o]}", fontsize=15
        )
        figs.append(fig)
    return figs


def plot_community_uptake_graph(model, df, names: dict = dict(), cmap="viridis"):
    models = model.models
    model_name = []
    for m in model.models:
        if m.id in names:
            model_name.append(names[m.id])
        else:
            model_name.append(m.id.split("_")[0])

    names = np.array(model_name)
    df_in = df["Shuttle Reaction"]
    shared_output = dict()
    for i, data in df.iterrows():
        data = data[:-1]
        x = data.to_numpy()
        y = df_in[i]
        if y < 0:
            inputs = x < 0
            input_names = names[inputs]
            fluxes = x[inputs]
            if inputs.sum() > 0:
                shared_output[i] = (input_names, fluxes)

    G = nx.DiGraph()
    # Build nodes
    cmap = matplotlib.cm.get_cmap(cmap)
    G.add_nodes_from(names)
    G.add_nodes_from(list(shared_output.keys()))
    colors = [cmap(i / len(names)) for i in range(len(names))] + ["Grey"] * len(
        shared_output
    )
    widths = []
    edge_color = []
    for ex, (name, f) in shared_output.items():
        for i in range(len(name)):
            n = name[i]
            flux = f[i]
            G.add_edge(ex, n, weight=flux)
            widths.append(flux / 4)
            edge_color.append(cmap(np.argmax(names == n) / len(names)))

    pos = bipartite_layout(G, names)
    fig = plt.figure(figsize=(10, 30))
    plt.title("Shared Uptake", fontsize=30)
    nx.draw(
        G,
        with_labels=True,
        pos=pos,
        node_size=1000,
        font_size=8,
        width=widths,
        node_color=colors,
        edge_color=edge_color,
    )
    fig.tight_layout()

    return fig


def plot_community_interaction(model, df, names: dict = dict(), cmap: str = None):
    """This plots the community interaction as a graph with circular layout, similar to
    circos plots



        Args:
            model: Community model (Only implemented for ShuttleCommunity)
            df: Summary dataframe.

        Returns:
            figure: Plot

    """
    model_name = []
    for m in model.models:
        if m.id in names:
            model_name.append(names[m.id])
        else:
            model_name.append(m.id.split("_")[0])

    G, df = compute_community_interaction_graph(model, df)
    # Colors
    cmap = matplotlib.cm.get_cmap(cmap)
    # Build edges
    linewidths = []
    for ex, data in df.iterrows():
        idx = np.arange(len(df.columns))
        data = np.array(data)
        producer = idx[data > 0]
        consumer = idx[data < 0]
        for p in producer:
            node1 = ex[3:-2] + f"_{p}"
            for c in consumer:
                node2 = ex[3:-2] + f"_{c}"
                G.add_edge(node1, node2, weight=data[p])
                linewidths.append(data[p])

    widths = np.array(linewidths)
    widths /= widths.sum()
    widths[widths < 0.01] = 0.01

    colors = []
    for n in G.nodes:
        i = int(n[-1])
        colors.append(cmap(i / len(model.models)))

    # Circular interaction plot
    N = len(G.nodes)
    fig = plt.figure(figsize=(int(N / 10) + 10, int(N / 10) + 10))
    pos = circular_layout(G, scale=1, center=None, dim=2)
    nx.draw(
        G,
        pos=pos,
        with_labels=True,
        node_size=800,
        font_size=8,
        node_color=colors,
        width=widths * 20,
    )
    pathes = []
    for i in range(len(model.models)):
        pathes.append(
            matplotlib.patches.Patch(
                color=cmap(i / len(model.models)),
                label=model_name[i],
            )
        )
    fig.suptitle("Community Interaction\n", fontsize=20)
    plt.legend(handles=pathes)
    return fig


def plot_pairwise_growth_relation_per_weight(model, names: dict = dict()):
    """Plots all pairwise growth relationships. for all possible weights $(\alpha,
    1-\alpha)$.



        Args:
            model: Community model
            names: Dictionary of model names to display. If empty we will use the model id!

        Returns:
            figure: Plot

    """
    N = len(model.models)
    growth_dict = dict()
    alphas = None
    for i in range(N):
        for j in range(i + 1, N):
            alphas, growth1, growth2 = compute_pairwise_growth_relation_per_weight(
                model, i, j
            )
            growth_dict[(i, j)] = (growth1, growth2)
            growth_dict[(j, i)] = (growth2, growth1)
    model_name = []
    for model in model.models:
        if model.id in names:
            model_name.append(names[model.id])
        else:
            model_name.append(model.id.split("_")[0])

    fig, axes = plt.subplots(N - 1, N - 1, figsize=(15, 15), sharey=True)
    for i in range(len(axes)):
        axes[i, i].set_xlabel(r"$\alpha$ weight")
        axes[i, i].yaxis.set_tick_params(labelleft=True)
        for j in range(i + 1, len(axes[i]) + 1):
            axes[0, j - 1].set_title(model_name[j] + "\n", fontsize=20)
            if j == i + 1:
                axes[i, -1].set_ylabel("\n" + (model_name[i]), fontsize=20)
                axes[i, -1].yaxis.set_label_position("right")
                ax2 = axes[i, j - 1].twinx()
                ax2.set_ylabel("Growth \n \n \n")
                ax2.yaxis.set_label_position("left")
                ax2.set_yticklabels([])
                ax2.set_yticks([])
            growth1, growth2 = growth_dict[(i, j)]
            axes[i, j - 1].plot(alphas, growth1, color="black")
            axes[i, j - 1].plot(alphas, growth2, color="black", linestyle=":")
            if j < N - 1:
                axes[j, i].axis("off")
    fig.tight_layout()
    return fig
