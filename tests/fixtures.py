def sample_players():
    return {
        "1": {"full_name": "Bijan Robinson", "position": "RB", "team": "ATL", "age": 24, "search_rank": 4, "active": True, "depth_chart_order": 1},
        "2": {"full_name": "Ja'Marr Chase", "position": "WR", "team": "CIN", "age": 26, "search_rank": 5, "active": True, "depth_chart_order": 1},
        "3": {"full_name": "Brock Bowers", "position": "TE", "team": "LV", "age": 23, "search_rank": 22, "active": True, "depth_chart_order": 1},
        "4": {"full_name": "Josh Allen", "position": "QB", "team": "BUF", "age": 30, "search_rank": 18, "active": True, "depth_chart_order": 1},
        "5": {"full_name": "Bench Kicker", "position": "K", "team": "DAL", "age": 28, "search_rank": 175, "active": True},
        "6": {"full_name": "Hurt Runner", "position": "RB", "team": "SF", "age": 31, "search_rank": 8, "active": True, "injury_status": "Out"},
        "7": {"full_name": "Drake London", "position": "WR", "team": "ATL", "age": 25, "search_rank": 20, "active": True, "depth_chart_order": 1},
        "8": {"full_name": "Trey McBride", "position": "TE", "team": "ARI", "age": 26, "search_rank": 35, "active": True, "depth_chart_order": 1},
    }


def sample_draft():
    return {
        "draft_id": "mock-draft",
        "type": "snake",
        "status": "drafting",
        "league_id": "league-1",
        "settings": {
            "teams": 4,
            "rounds": 10,
            "slots_qb": 1,
            "slots_rb": 2,
            "slots_wr": 2,
            "slots_te": 1,
            "slots_flex": 1,
            "slots_k": 1,
            "slots_def": 1,
        },
        "metadata": {"scoring_type": "ppr"},
        "draft_order": {"user-1": 2},
    }


def sample_picks():
    return [
        {"player_id": "1", "draft_slot": 1, "pick_no": 1, "round": 1, "metadata": {"position": "RB", "first_name": "Bijan", "last_name": "Robinson"}},
    ]
