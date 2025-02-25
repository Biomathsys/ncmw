from typing import List, Tuple, Iterable
from cobra import Model, Reaction, Metabolite
import re

import pandas as pd
import numpy as np

from ncmw.utils import pad_dict_list


def transport_reactions(model: Model) -> List[str]:
    """This function return a list of potential transport reactions, we define a
    transport reaction as a reaction which contains metabolites from atleast two different compartments!

        Args:
            model (Model): A cobra model

        Returns:
            list: List of names that potentially are transport reaction
    """
    compartment_name = ["_" + id for id in model.compartments.keys()]
    res = []
    for rec in model.reactions:
        for i, c1 in enumerate(compartment_name):
            for c2 in compartment_name[i + 1 :]:
                if c1 in rec.reaction and c2 in rec.reaction:
                    res.append(rec.id)
    return res


def table_ex_transport(model: Model) -> pd.DataFrame:
    """This method checks if all exchange reaction has an associated transporter

    Args:
        model (Model): Cobra model

    Returns:
        pd.DataFrame: Table of indicators (0 indicates abscence, 1 indicates presence)
    """
    compartments = [id for id in model.compartments.keys()]
    metabolites_ex = [key[3:-2] for key in model.medium]
    metabolites_comp = []
    transport_reaction = transport_reactions(model)
    for c in compartments:
        metabolites_comp.append(
            [met for met in model.metabolites if c in met.compartment]
        )
    df = dict(
        zip(
            metabolites_ex,
            [[0 for _ in range(len(compartments))] for _ in range(len(metabolites_ex))],
        )
    )

    for met in metabolites_ex:
        met_id = re.compile(str(met) + "_.")
        hits = []
        for met_c in metabolites_comp:
            hits.append(list(filter(lambda x: re.match(met_id, x.id), met_c)))
        for i, hits_c in enumerate(hits):
            for hit in hits_c:
                for rec in [rec.id for rec in hit.reactions]:
                    if rec in transport_reaction:
                        df[met][i] = 1
    df = pd.DataFrame(df).T
    df.columns = compartments
    return df


def sekretion_uptake_fba(model: Model) -> Tuple[List[str], List[str]]:
    """This gives the uptake and sekretion reaction in a FBA solution

    NOTE: This is not unique! Use the method base on FVA instead for unique solutions.

    Args:
        model (Model): A cobra model

    Returns:
        list: List of uptake reactions
        list: List of sekretion reactions
    """
    summary = model.summary()
    uptake = [
        id
        for id in summary.uptake_flux.index
        if summary.uptake_flux.loc[id]["flux"] > 0
    ]
    sekretion = [
        id
        for id in summary.secretion_flux.index
        if summary.secretion_flux.loc[id]["flux"] < 0
    ]
    return uptake, sekretion


def sekretion_uptake_fva(fva) -> Tuple[List, List]:
    """This computes the uptake and sekreation reaction using FVA, this is UNIQUE!

    Args:
        fva (DataFrame): Fva results

    Returns:
        list: List of uptake reactions
        list: List of sekretion reactions
    """
    ex_fva = fva.loc[fva.index.str.contains("EX_")]
    uptake = ex_fva[ex_fva["minimum"] < 0].index.tolist()
    sekretion = ex_fva[ex_fva["maximum"] > 0].index.tolist()
    return uptake, sekretion


def compute_uptake_sekretion_table(
    model_name1: str,
    model_name2: str,
    uptake1: List[str],
    uptake2: List[str],
    sekretion1: List[str],
    sekretion2: List[str],
) -> pd.DataFrame:
    """Constructs a table of the uptake sekretion and overlap for a pair of models

    Args:
        model_name1: Name of the model 1
        model_name2: Name of the model 2
        uptake1: Uptake reactions of model 1
        uptake2: Uptake reactions of model 2
        sekretion1: Sekretion reactions of model 1
        sekretion2: Sekretion reactions of model 2

    Returns:
        pd.DataFrame: Tabel of uptake/sekretions as well as Sekretion -> Uptake relationships.

    """
    # Common up/sekretion from SA to DP
    sek2_up1 = []
    for sek in sekretion2:
        for up in uptake1:
            if str(sek) == str(up):
                sek2_up1.append(str(sek))
    sek1_up2 = []
    for sek in sekretion1:
        for up in uptake2:
            if str(sek) == str(up):
                sek1_up2.append(str(sek))
    df_dict = {
        f"{model_name1} Uptake": uptake1,
        f"{model_name1} Secretion": sekretion1,
        f"{model_name1} -> {model_name2}": sek1_up2,
        f"{model_name2} -> {model_name1}": sek2_up1,
        f"{model_name2} Secretion": sekretion2,
        f"{model_name2} Uptake": uptake2,
    }
    df_dict = pad_dict_list(df_dict, "na")
    df = pd.DataFrame(df_dict)
    return df


def compute_all_uptake_sekretion_tables(
    models: List[Model], fvas: List[pd.DataFrame] = None
) -> List[pd.DataFrame]:
    """Computes all uptake sekretion tables for all models.

    Args:
        models: Cobra models
        fvas: FVA results

    Returns:
        list : List of tables.

    """
    N = len(models)
    if fvas is not None:
        assert len(fvas) == len(models)
    dfs = []
    for i in range(N):
        for j in range(i + 1, N):
            if fvas is None:
                df = compute_uptake_sekretion_table(
                    models[i].id,
                    models[j].id,
                    *sekretion_uptake_fba(models[i]),
                    *sekretion_uptake_fba(models[j]),
                )
            else:
                df = compute_uptake_sekretion_table(
                    models[i].id,
                    models[j].id,
                    *sekretion_uptake_fva(fvas[i]),
                    *sekretion_uptake_fva(fvas[j]),
                )
            dfs.append(df)
    return dfs


def compute_uptake_growth_relationship(
    model: Model, ids: List[str], h: int = 100, custom_flux: Iterable = None
) -> Tuple[Iterable, Iterable]:
    """For each reaction in with id contained in "ids" the method keeps all other
    components within the medium constant but changes this one from a certain value to zero.

    This can be used for a sensitivity analysis, as if certain metabolites are important
    within the medium we expect that they strongly influence the growth!

        Returns:
            list: Fluxes used to compute the corresponding growths.
            list: Growths computed using the corresponding fluxes.

    """
    medium = model.medium.copy()
    fluxes = []
    growths = []
    for up in ids:
        if up in medium:
            old_f = medium[up]
        else:
            old_f = 0
        flux = np.linspace(old_f, 0, h)
        if not custom_flux is None:
            flux = custom_flux
        growth = []
        with model:
            for f in flux:
                medium[up] = f
                model.medium = medium
                growth.append(model.slim_optimize())
            medium[up] = old_f
            fluxes.append(flux)
            growths.append(np.array(growth))
    return fluxes, growths
