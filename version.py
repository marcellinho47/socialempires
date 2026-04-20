import random

from engine import timestamp_now

version_name = "alpha 0.05"
version_code = "0.05a"

# Item IDs that belong to battle/campaign maps (enemies, battle-only buildings).
# When the SWF opens a battle (e.g. rescue princess), it spams CMD_BUY with
# bool_dont_modify_resources=1 to place these; the old handler persisted them
# into the player's village save. The 0.04a→0.05a migration scrubs them.
_BATTLE_ITEM_IDS = {
    83,   # Prisoner Princess
    135,  # Troll Cave
    291,  # Troll Tower I
    292,  # Troll Tower II (guess — same family)
    305,  # Troll Wall II
    304,  # Troll Wall I (guess)
    525,  # Small Troll
    526,  # Devious Troll
    527,  # Big Troll
    530,  # Axethrower
}

def migrate_loaded_save(save: dict) -> bool:

    # discard current version saves
    if save["version"] == version_code:
        return False
    
    # fix 0.01a saves
    if "version" not in save or save["version"] is None:
        save["version"] = "0.01a"
    
    # 0.01a -> 0.02a
    if save["version"] == "0.01a":
        save["maps"][0]["timestamp"] = timestamp_now()
        save["privateState"]["dartsRandomSeed"] = abs(int((2**16 - 1) * random.random()))
        save["version"] = "0.02a"
        print("   > migrated to 0.02a")
    
    # 0.02a -> 0.03a
    if save["version"] == "0.02a":
        if "arrayAnimals" not in save["privateState"]:
            save["privateState"]["arrayAnimals"] = {} # fix no animal spawning
        if "strategy" not in save["privateState"]:
            save["privateState"]["strategy"] = 8 # fix crash when attacking a player
        if "universAttackWin" not in save["maps"][0]:
            save["maps"][0]["universAttackWin"] = [] # pvp current island progress
        if "questTimes" not in save["maps"][0]:
            save["maps"][0]["questTimes"] = [] # quests
        if "lastQuestTimes" not in save["maps"][0]:
            save["maps"][0]["lastQuestTimes"] = [] # 1.1.5 quests
        save["version"] = "0.03a"
        print("   > migrated to 0.03a")
    
    # 0.03a -> 0.04a
    if save["version"] == "0.03a":
        if "pic" not in save["playerInfo"].keys():
            save["playerInfo"]["pic"] = ""
        if("survivalVidaTimeStamp" not in save["privateState"]):
            save["privateState"]["survivalVidaTimeStamp"] = []
        if("survivalVidasExtra" not in save["privateState"]):
            save["privateState"]["survivalVidasExtra"] = 0
        if("survivalMaps" not in save["privateState"]):
            save["privateState"]["survivalMaps"] = {
                "100000035": {
                    "ts": 0,
                    "tp": 0
                },
                "100000036": {
                    "ts": 0,
                    "tp": 0
                },
                "100000037": {
                    "ts": 0,
                    "tp": 0
                }
            }
        save["version"] = "0.04a"
        print("   > migrated to 0.04a")

    # 0.04a -> 0.05a: scrub battle enemies accidentally persisted from
    # rescue-princess / troll campaigns by the old CMD_BUY handler.
    if save["version"] == "0.04a":
        scrubbed = 0
        for m in save.get("maps", []):
            items = m.get("items", [])
            kept = [it for it in items if (len(it) > 0 and it[0] not in _BATTLE_ITEM_IDS)]
            scrubbed += len(items) - len(kept)
            m["items"] = kept
        if scrubbed:
            print(f"   > 0.05a cleanup: removed {scrubbed} battle items from map(s)")
        save["version"] = "0.05a"
        print("   > migrated to 0.05a")

    return True