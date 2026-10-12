# SPDX-License-Identifier: GPL-3.0-only
"""Native Player_Skills identities in the unchanged SETS button order.

Keys were copied from the .24 Captain read; icons are presentation resources.
Only a matching definition in the current observation establishes an unowned node.
"""

SPACE = {
    "eng": [
        ("Engineering_T1", "Hull_Healing", ("1", "2", "3")),
        ("Engineering_T1", "Hull_Hp", ("1", "2", "3")),
        ("Engineering_T2", "Eps", ("1", "2", "3")),
        ("Engineering_T2", "Impulse_Engines", ("1", "2", "3")),
        ("Engineering_T3", "Dmg_Res", ("1", "2a", "2b")),
        ("Engineering_T3", "Hull_Regen", ("1", "2", "3")),
        ("Engineering_T4", "Shld_Aux_Pwr", ("1", "2a", "2b")),
        ("Engineering_T4", "Wpn_Eng_Pwr", ("1", "2a", "2b")),
        ("Engineering_T5", "All_Pwr", ("1", "2a", "2b")),
        ("Engineering_T5", "Eng_Boff_Cd", ("1", "2", "3")),
    ],
    "sci": [
        ("Science_T1", "Shield_Healing", ("1", "2", "3")),
        ("Science_T1", "Shield_Hp", ("1", "2", "3")),
        ("Science_T2", "Control_Exp", ("1", "2a", "2b")),
        ("Science_T2", "Drain_Exp", ("1", "2a", "2b")),
        ("Science_T3", "Shield_Regen", ("1", "2", "3")),
        ("Science_T3", "Shield_Res", ("1", "2", "3")),
        ("Science_T4", "Exotic_Dmg", ("1", "2", "3")),
        ("Science_T4", "Wpn_Range", ("1", "2", "3")),
        ("Science_T5", "Sci_Boff_Cd", ("1", "2", "3")),
        ("Science_T5", "Shield_Mastery", ("1", "2a", "2b")),
    ],
    "tac": [
        ("Tactical_T1", "Energy_Wpn_Dmg", ("1", "2", "3")),
        ("Tactical_T1", "Proj_Wpn_Dmg", ("1", "2", "3")),
        ("Tactical_T2", "Accuracy", ("1", "2", "3")),
        ("Tactical_T2", "Defense", ("1", "2", "3")),
        ("Tactical_T3", "Wpn_Critd", ("1", "2", "3")),
        ("Tactical_T3", "Wpn_Crith", ("1", "2", "3")),
        ("Tactical_T4", "Hull_Penetrate", ("1", "2", "3")),
        ("Tactical_T4", "Shield_Penetrate", ("1", "2", "3")),
        ("Tactical_T5", "Pet_Buff", ("1", "2a", "2b")),
        ("Tactical_T5", "Tac_Boff_Cd", ("1", "2", "3")),
    ],
}
GROUND = [
    ("Ground_Skills_C1", ("Wpn_Dmg", "Wpn_Crits", "Wpn_Penetrate")),
    ("Ground_Skills_C2", ("Hp_Max", "Armor", "Hp_Regen")),
    ("Ground_Skills_C3", ("Psg", "Psg_Harden")),
    ("Ground_Skills_C4", ("Kit_Perf", "Kit_Cd")),
]
SPACE_UNLOCKS = {
    "eng": [("Eng_Unlocks_1", ("Pet_Health", "Battery_Expertise")),
            ("Eng_Unlocks_2", ("Hull_Hp", "Subsys_Repair")),
            ("Eng_Unlocks_3", ("Engine_Pwr", "Shld_Pwr")),
            ("Eng_Unlocks_4", ("Wpn_Pwr", "Aux_Pwr")),
            ("Engineering_Ultimate", ("Eng_Ultimate", "Eng_Ult_Enh_1", "Eng_Ult_Enh_2", "Eng_Ult_Enh_3"))],
    "sci": [("Sci_Unlocks_1", ("Sector_Speed", "Transwarp_Cd")),
            ("Sci_Unlocks_2", ("Shield_Hp", "Stealth")),
            ("Sci_Unlocks_3", ("Perception", "Control_Resist")),
            ("Sci_Unlocks_4", ("Shld_Drain_Resist", "Pwr_Drain_Resist")),
            ("Science_Ultimate", ("Sci_Ultimate", "Sci_Ult_Enh_1", "Sci_Ult_Enh_2", "Sci_Ult_Enh_3"))],
    "tac": [("Tactical_Unlocks_1", ("Pet_Damage", "Threat_Control")),
            ("Tactical_Unlocks_2", ("Proj_Crit_H", "Proj_Crit_D")),
            ("Tactical_Unlocks_3", ("Energy_Crit_H", "Energy_Crit_D")),
            ("Tactical_Unlocks_4", ("Accuracy", "Defense")),
            ("Tactical_Ultimate", ("Tac_Ultimate", "Tac_Ult_Enh_1", "Tac_Ult_Enh_2", "Tac_Ult_Enh_3"))],
}
GROUND_UNLOCKS = [("Control_Res", "Devices"), ("Improved_Aim", "Improved_Crouch"),
                  ("Melee_Speed", "Melee_Dmg"), ("Flank_Dmg", "Flank_Res"), ("Dmg_Crit", "Res_Hp_Shld")]


def skill_layout():
    return {
        "space": {career: [{"id": f"Player_Skills_Space.{group}.{node}_{rank}"}
                            for group, node, ranks in entries for rank in ranks]
                  for career, entries in SPACE.items()},
        "ground": [[{"id": f"Player_Skills_Ground.{group}.{node}_{rank}"}
                    for node in nodes for rank in (1, 2)] for group, nodes in GROUND],
        "unlocks": {
            "space": {career: [[{"id": f"Player_Skills_Space.{group}.{node}"} for node in nodes]
                               for group, nodes in groups] for career, groups in SPACE_UNLOCKS.items()},
            "ground": [[{"id": f"Player_Skills_Ground.Ground_Unlocks_{i}.{node}"} for node in nodes]
                       for i, nodes in enumerate(GROUND_UNLOCKS, 1)],
        },
    }
