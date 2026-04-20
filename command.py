import json
import datetime

from sessions import session, save_session
from get_game_config import get_game_config, get_level_from_xp, get_name_from_item_id, get_attribute_from_mission_id, get_xp_from_level, get_attribute_from_item_id, get_item_from_subcat_functional
from constants import Constant
from engine import apply_cost, apply_collect, apply_collect_xp, timestamp_now

def get_strategy_type(id):
    if id == 8:
        return "Defensive"
    if id == 9:
        return "Mid Defensive"
    if id == 7:
        return "Mid Aggressive"
    if id == 10:
        return "Aggressive"
    return "Unknown Strategy"

def command(USERID, data):
    timestamp = data["ts"]
    first_number = data["first_number"]
    accessToken = data["accessToken"]
    tries = data["tries"]
    publishActions = data["publishActions"]
    commands = data["commands"]

    for i, comm in enumerate(commands):
        cmd = comm["cmd"]
        args = comm["args"]
        try:
            do_command(USERID, cmd, args)
        except (IndexError, KeyError, TypeError, ValueError) as e:
            print(f"\n [!] COMMAND FAILED: cmd={cmd} args={args} -> {type(e).__name__}: {e}")
    save_session(USERID) # Save session

def do_command(USERID, cmd, args):
    save = session(USERID)
    print (" [+] COMMAND: ", cmd, "(", args, ") -> ", sep='', end='')

    if cmd == Constant.CMD_GAME_STATUS:
        print(" ".join(args))

    elif cmd == Constant.CMD_BUY:
        id = args[0]
        x = args[1]
        y = args[2]
        frame = args[3] # TODO ??
        town_id = args[4]
        bool_dont_modify_resources = bool(args[5]) # 1 if the game "buys" for you, so does not substract whatever the item cost is.
        price_multiplier = args[6]
        type = args[7]
        print("Add", str(get_name_from_item_id(id)), "at", f"({x},{y})", "free" if bool_dont_modify_resources else "paid")
        collected_at_timestamp = timestamp_now()
        level = 0 # TODO
        orientation = 0
        map = save["maps"][town_id]
        if bool_dont_modify_resources:
            # The client is telling us the placement is game-generated
            # (campaign enemies, quest cutscenes, event setup). Don't charge
            # and — critically — don't persist it. The log shows these floods
            # during battles: Troll Wall II, Axethrower, Prisoner Princess,
            # etc. at battle-map coordinates. Persisting them corrupts the
            # village save and makes the game re-offer the same mission on
            # next login (because the unfinished-looking battle is still
            # "in progress" from the save's perspective).
            # Trade-off: if a legitimate gift/event placement uses bool=1
            # (e.g. a quest-reward free building), it also won't persist —
            # to be revisited if that turns out to be a real pattern. For
            # now, the battle-pollution case is the observed one.
            return
        apply_cost(save["playerInfo"], map, id, price_multiplier)
        xp = int(get_attribute_from_item_id(id, "xp"))
        map["xp"] = map["xp"] + xp
        map["items"] += [[id, x, y, orientation, collected_at_timestamp, level]]
    
    elif cmd == Constant.CMD_COMPLETE_TUTORIAL:
        tutorial_step = args[0]
        print("Tutorial step", tutorial_step, "reached.")
        if tutorial_step >= 31: # 31 is Dragon choosing. After that, you have some freedom. There's at least until step 45.
            print("Tutorial COMPLETED!")
            save["playerInfo"]["completed_tutorial"] = 1
            save["privateState"]["dragonNestActive"] = 1 
    
    elif cmd == Constant.CMD_MOVE:
        ix = args[0]
        iy = args[1]
        id = args[2]
        newx = args[3]
        newy = args[4]
        frame = args[5]
        town_id = args[6]
        reason = args[7] # "Unitat", "moveTo", "colisio", "MouseUsed"
        print("Move", str(get_name_from_item_id(id)), "from", f"({ix},{iy})", "to", f"({newx},{newy})")
        map = save["maps"][town_id]
        for item in map["items"]:
            if item[0] == id and item[1] == ix and item[2] == iy:
                item[1] = newx
                item[2] = newy
                break
    
    elif cmd == Constant.CMD_COLLECT:
        x = args[0]
        y = args[1]
        town_id = args[2]
        id = args[3]
        num_units_contained_when_harvested = args[4]#TODO does this affect multiplier?
        resource_multiplier = float(args[5])
        cash_to_substract = int(args[6])
        # CHE-6: cap multiplier — legit "mouseUsed" booster is 5x, anything above is cheat
        if resource_multiplier < 0:
            resource_multiplier = 0
        MAX_COLLECT_MULT = 5.0
        if resource_multiplier > MAX_COLLECT_MULT:
            print(f"  CMD_COLLECT: multiplier capped {resource_multiplier} -> {MAX_COLLECT_MULT}")
            resource_multiplier = MAX_COLLECT_MULT
        # Also cap the booster cost claim (client-supplied)
        cash_to_substract = max(0, min(cash_to_substract, 10))
        print("Collect", str(get_name_from_item_id(id)))
        map = save["maps"][town_id]
        apply_collect(save["playerInfo"], map, id, resource_multiplier)
        save["playerInfo"]["cash"] = max(save["playerInfo"]["cash"] - cash_to_substract, 0)
        # Reset the item's collected_at_timestamp so its production cooldown
        # starts over. Without this, the mine/field on the map keeps its
        # original timestamp forever and the client can't reason about
        # readiness across sessions.
        now_ts = timestamp_now()
        for item in map["items"]:
            if item[0] == id and item[1] == x and item[2] == y:
                if len(item) > 4:
                    item[4] = now_ts
                break
    
    elif cmd == Constant.CMD_SELL:
        x = args[0]
        y = args[1]
        id = args[2]
        town_id = args[3]
        bool_dont_modify_resources = args[4]
        reason = args[5]
        if reason == 'CLEAN_0':
            # Battle setup cleanup: the SWF clears items inside the area
            # where the campaign/attack map will render. This is ephemeral,
            # the items belong to the player's real village and must not
            # be removed from the save. Re-placements that follow come as
            # CMD_BUY bool=1 (also ignored), so the net effect is
            # "village state untouched while the battle runs client-side".
            print(f"  CMD_SELL CLEAN_0 ignored for {get_name_from_item_id(id)} at ({x},{y}) — ephemeral battle cleanup")
            return
        print("Remove", str(get_name_from_item_id(id)), "from", f"({x},{y}). Reason: {reason}")
        map = save["maps"][town_id]
        for item in map["items"]:
            if item[0] == id and item[1] == x and item[2] == y:
                map["items"].remove(item)
                break
        if not bool_dont_modify_resources:
            price_multiplier = -0.05
            if get_attribute_from_item_id(id, "cost_type") != "c":
                apply_cost(save["playerInfo"], save["maps"][town_id], id, price_multiplier)
        if reason == 'KILL':
            pass # TODO : add to graveyard
    
    elif cmd == Constant.CMD_KILL:
        x = args[0]
        y = args[1]
        id = args[2]
        town_id = args[3]
        type = args[4]
        print("Kill", str(get_name_from_item_id(id)), "from", f"({x},{y}).")
        map = save["maps"][town_id]
        for item in map["items"]:
            if item[0] == id and item[1] == x and item[2] == y:
                # C.3: remember the level at death so resurrect can restore it.
                # item tuple: [item_id, x, y, orientation, collected_at, level, ...]
                level_at_death = int(item[5]) if len(item) > 5 else 0
                if level_at_death > 0:
                    save["privateState"].setdefault("hero_levels", {})[str(id)] = level_at_death
                apply_collect_xp(map, id)
                map["items"].remove(item)
                break
    
    elif cmd == Constant.CMD_COMPLETE_MISSION:
        mission_id = args[0]
        skipped_with_cash = bool(args[1])
        # CHE-2: ignore duplicates (client could spam to re-complete)
        if mission_id in save["privateState"].get("completedMissions", []):
            print(f"  Mission {mission_id} already completed, skipping")
            return
        print("Complete mission", mission_id, ":", str(get_attribute_from_mission_id(mission_id, "title")))
        if skipped_with_cash:
            # C.1: Mission config has no skip_price field. Heuristic: proportional
            # to the gold reward (richer missions cost more to skip). Clamp 1..25.
            reward = int(get_attribute_from_mission_id(mission_id, "reward") or 0)
            skip_cost = max(1, min(25, reward // 200))
            save["playerInfo"]["cash"] = max(save["playerInfo"]["cash"] - skip_cost, 0)
            print(f"  Skipped with cash: -{skip_cost}")
        save["privateState"]["completedMissions"] += [mission_id]

    elif cmd == Constant.CMD_REWARD_MISSION:
        town_id = args[0]
        mission_id = args[1]
        # CHE-2: reject re-claim — prevents infinite reward farming
        if mission_id in save["privateState"].get("rewardedMissions", []):
            print(f"  Mission {mission_id} already rewarded, skipping")
            return
        print("Reward mission", mission_id, ":", str(get_attribute_from_mission_id(mission_id, "title")))
        reward = int(get_attribute_from_mission_id(mission_id, "reward")) # gold
        save["maps"][town_id]["coins"] += reward
        save["privateState"]["rewardedMissions"] += [mission_id]
    
    elif cmd == Constant.CMD_PUSH_UNIT:
        unit_x = args[0]
        unit_y = args[1]
        unit_id = args[2]
        b_x = args[3]
        b_y = args[4]
        town_id = args[5]
        print("Push", str(get_name_from_item_id(unit_id)), "to", f"({b_x},{b_y}).")
        map = save["maps"][town_id]
        # Unit into building
        for item in map["items"]:
            if item[1] == b_x and item[2] == b_y:
                if len(item) < 7:
                    item += [[]]
                item[6] += [unit_id]
                break
        # Remove unit
        for item in map["items"]:
            if item[0] == unit_id and item[1] == unit_x and item[2] == unit_y:
                map["items"].remove(item)
                break
    
    elif cmd == Constant.CMD_POP_UNIT:
        b_x = args[0]
        b_y = args[1]
        town_id = args[2]
        unit_id = args[3]
        place_popped_unit = len(args) > 4
        if place_popped_unit:
            unit_x = args[4]
            unit_y = args[5]
            unit_frame = args[6] # unknown use
        print("Pop", str(get_name_from_item_id(unit_id)), "from", f"({b_x},{b_y}).")
        map = save["maps"][town_id]
        # Remove unit from building
        for item in map["items"]:
            if item[1] == b_x and item[2] == b_y:
                if len(item) < 7:
                    break
                item[6].remove(unit_id)
                break
        if place_popped_unit:
            # Spawn unit outside
            collected_at_timestamp = timestamp_now()
            level = 0 # TODO 
            orientation = 0
            map["items"] += [[unit_id, unit_x, unit_y, orientation, collected_at_timestamp, level]]
    
    elif cmd == Constant.CMD_RT_LEVEL_UP:
        requested_level = int(args[0])
        map = save["maps"][0] # TODO : xp must be general, since theres no given town_id
        current_level = int(map.get("level", 1))
        # CHE-3: cap level-up at +1 per command; client can't jump 99 levels
        new_level = min(requested_level, current_level + 1)
        if new_level != requested_level:
            print(f"Level Up capped: requested {requested_level}, granted {new_level} (was {current_level})")
        else:
            print("Level Up!:", new_level)
        map["level"] = new_level
        current_xp = map["xp"]
        min_expected_xp = get_xp_from_level(max(0, new_level - 1))
        map["xp"] = max(min_expected_xp, current_xp) # try to fix problems with not counting XP... by keeping up with client-side level counting
        # Apply level-up reward from game config (c=cash, g=gold, w=wood, f=food, s=stone)
        try:
            level_info = get_game_config()["levels"][int(new_level)]
            rtype = level_info.get("reward_type")
            amount = int(level_info.get("reward_amount", 0))
            if amount > 0:
                if rtype == "c":
                    save["playerInfo"]["cash"] += amount
                elif rtype == "g":
                    map["coins"] += amount
                elif rtype == "w":
                    map["wood"] += amount
                elif rtype == "f":
                    map["food"] += amount
                elif rtype == "s":
                    map["stone"] += amount
                print(f"  Level-up reward: +{amount} {rtype}")
        except (IndexError, KeyError, TypeError, ValueError) as e:
            print(f"  Level-up reward skipped: {e}")

    elif cmd == Constant.CMD_RT_PUBLISH_SCORE:
        new_xp = args[0]
        print("xp set to", new_xp)
        map = save["maps"][0] # TODO : xp must be general, since theres no given town_id
        map["xp"] = new_xp
        map["level"] = get_level_from_xp(new_xp)

    elif cmd == Constant.CMD_EXPAND:
        land_id = args[0]
        resource = args[1]
        town_id = int(args[2])
        print("Expansion", land_id, "purchased")
        map = save["maps"][town_id]
        if land_id in map["expansions"]:
            return
        # Substract resources
        expansion_prices = get_game_config()["expansion_prices"]
        exp = expansion_prices[len(map["expansions"]) - 1]
        if resource == "gold":
            to_substract = exp["coins"]
            save["maps"][town_id]["coins"] = max(save["maps"][town_id]["coins"] - to_substract, 0)
        elif resource == "cash":
            to_substract = exp["cash"]
            save["playerInfo"]["cash"] = max(save["playerInfo"]["cash"] - to_substract, 0)
        # Add expansion
        map["expansions"].append(land_id)

    elif cmd == Constant.CMD_NAME_MAP:
        town_id =int(args[0])
        new_name = args[1]
        print(f"Map name changed to '{new_name}'.")
        save["playerInfo"]["map_names"][town_id] = new_name

    elif cmd == Constant.CMD_EXCHANGE_CASH:
        town_id = args[0]
        # CHE-8: cap to 10 exchanges per rolling 24h — prevents infinite cash→gold loop.
        EXCHANGE_DAILY_LIMIT = 10
        EXCHANGE_WINDOW_SEC = 24 * 3600
        ps = save["privateState"]
        now = timestamp_now()
        last_reset = ps.get("exchangeCashResetAt", 0)
        if now - last_reset >= EXCHANGE_WINDOW_SEC:
            ps["exchangeCashCount"] = 0
            ps["exchangeCashResetAt"] = now
        count = ps.get("exchangeCashCount", 0)
        if count >= EXCHANGE_DAILY_LIMIT:
            print(f"  Exchange denied: daily limit ({EXCHANGE_DAILY_LIMIT}) reached")
            return
        ps["exchangeCashCount"] = count + 1
        print(f"Exchange cash -> coins ({ps['exchangeCashCount']}/{EXCHANGE_DAILY_LIMIT} today)")
        save["playerInfo"]["cash"] = max(save["playerInfo"]["cash"] - 5, 0)
        save["maps"][town_id]["coins"] += 2500

    elif cmd == Constant.CMD_STORE_ITEM:
        x = args[0]
        y = args[1]
        town_id = int(args[2])
        item_id = args[3]
        print("Store", str(get_name_from_item_id(item_id)), "from", f"({x},{y})")
        map = save["maps"][town_id]
        for item in map["items"]:
            if item[0] == item_id and item[1] == x and item[2] == y:
                map["items"].remove(item)
                break
        length = len(save["privateState"]["gifts"])
        if length <= item_id:
            for i in range(item_id - length + 1):
                save["privateState"]["gifts"].append(0)
        save["privateState"]["gifts"][item_id] += 1

    elif cmd == Constant.CMD_PLACE_GIFT:
        item_id = args[0]
        x = args[1]
        y = args[2]
        town_id = args[3]#unsure, both 3 and 4 seem to stay 0
        args[4]#unknown yet
        print("Add", str(get_name_from_item_id(item_id)), "at", f"({x},{y})")
        items = save["maps"][town_id]["items"]
        orientation = 0#TODO
        collected_at_timestamp = timestamp_now()
        level = 0
        items += [[item_id, x, y, orientation, collected_at_timestamp, level]]#maybe make function for adding items
        save["privateState"]["gifts"][item_id] -= 1
        if save["privateState"]["gifts"][item_id] == 0: #removes excess zeros at end if necessary
            while(save["privateState"]["gifts"][-1] == 0):
                save["privateState"]["gifts"].pop()  

    elif cmd == Constant.CMD_SELL_GIFT:
        item_id = args[0]
        town_id = args[1]
        print("Gift", str(get_name_from_item_id(item_id)), "sold on town:",town_id)
        gifts = save["privateState"]["gifts"]
        gifts[item_id] -= 1
        if gifts[item_id] == 0: #removes excess zeros at end if necessary
            while(len(gifts) != 0 and gifts[-1] == 0):
                gifts.pop()
        price_multiplier = -0.05
        if get_attribute_from_item_id(item_id, "cost_type") != "c":
            apply_cost(save["playerInfo"], save["maps"][town_id], item_id, price_multiplier)
    
    elif cmd == Constant.CMD_ACTIVATE_DRAGON:
        currency = args[0]
        print("Dragon nest activated.")
        if currency == 'c':
            save["playerInfo"]["cash"] = max(int(save["playerInfo"]["cash"] - 50), 0)
        elif currency == 'g':
            map = save["maps"]
            map[0]["coins"] = max(int(map[0]["coins"] - 100000), 0)
        save["privateState"]["dragonNestActive"] = 1
        save["privateState"]["timeStampTakeCare"] = -1 # remove timer if any
    
    elif cmd == Constant.CMD_DESACTIVATE_DRAGON:
        print("Dragon nest deactivated.")
        pState = save["privateState"]
        pState["dragonNestActive"] = 0
        # reset step and dragon numbers
        pState["stepNumber"] = 0
        pState["dragonNumber"] = 0
        pState["timeStampTakeCare"] = -1 # remove timer if any

    elif cmd == Constant.CMD_NEXT_DRAGON_STEP:
        unknown = args[0]
        print("Dragon step increased.")
        pState = save["privateState"]
        pState["stepNumber"] += 1
        pState["timeStampTakeCare"] = timestamp_now()

    elif cmd == Constant.CMD_NEXT_DRAGON:
        print("Dragon step reset and dragonNumber increased.")
        pState = save["privateState"]
        pState["stepNumber"] = 0
        pState["dragonNumber"] += 1
        pState["timeStampTakeCare"] = -1 # remove timer

    elif cmd == Constant.CMD_DRAGON_BUY_STEP_CASH:
        # CHE-9: client sends price; enforce a minimum so they can't skip for free.
        price = max(int(args[0]), 5)
        print(f"Buy dragon step with cash ({price}).")
        save["playerInfo"]["cash"] = max(int(save["playerInfo"]["cash"] - price), 0)
        save["privateState"]["timeStampTakeCare"] = -1 # remove timer

    elif cmd == Constant.CMD_RIDER_BUY_STEP_CASH:
        price = max(int(args[0]), 5)
        print(f"Buy rider step with cash ({price}).")
        save["playerInfo"]["cash"] = max(int(save["playerInfo"]["cash"] - price), 0)
        save["privateState"]["riderTimeStamp"] = -1 # remove timer

    elif cmd == Constant.CMD_NEXT_RIDER_STEP:
        print("Rider step increased.")
        pState = save["privateState"]
        pState["riderStepNumber"] += 1
        pState["riderTimeStamp"] = timestamp_now()
    
    elif cmd == Constant.CMD_SELECT_RIDER:
        number = int(args[0])
        pState = save["privateState"]
        if number == 1 or number == 2 or number == 3:
            pState["riderNumber"] = number
            print("Rider", number, "Selected.")
        else:
            pState["riderNumber"] = 0
            pState["riderStepNumber"] = 0
            pState["riderTimeStamp"] = -1 # remove timer
            print("Rider reset.")
    
    elif cmd == Constant.CMD_ORIENT:
        x = args[0]
        y = args[1]
        new_orientation = args[2]
        town_id = args[3]
        print("Item at", f"({x},{y})", "changed to orientation", new_orientation)
        map = save["maps"][town_id]
        for item in map["items"]:
            if item[1] == x and item[2] == y:
                item[3] = new_orientation
                break
    
    elif cmd == Constant.CMD_MONSTER_BUY_STEP_CASH:
        price = max(int(args[0]), 5)
        print(f"Buy monster step with cash ({price}).")
        save["playerInfo"]["cash"] = max(int(save["playerInfo"]["cash"] - price), 0)
        save["privateState"]["timeStampTakeCareMonster"] = -1 # remove timer
    
    elif cmd == Constant.CMD_ACTIVATE_MONSTER:
        currency = args[0]
        print("Monster nest activated.")
        if currency == 'c':
            save["playerInfo"]["cash"] = max(int(save["playerInfo"]["cash"] - 50), 0)
        elif currency == 'g':
            map = save["maps"]
            map[0]["coins"] = max(int(map[0]["coins"] - 100000), 0)
        save["privateState"]["monsterNestActive"] = 1
        save["privateState"]["timeStampTakeCareMonster"] = -1 # remove timer if any
    
    elif cmd == Constant.CMD_DESACTIVATE_MONSTER: # cmd called too late
        print("Monster nest deactivated.")
        pState = save["privateState"]
        pState["monsterNestActive"] = 0
        pState["stepMonsterNumber"] = 0
        pState["MonsterNumber"] = 0
        pState["timeStampTakeCareMonster"] = -1 # remove timer if any


    elif cmd == Constant.CMD_NEXT_MONSTER_STEP:
        print("Monster Step increased.")
        pState = save["privateState"]
        pState["stepMonsterNumber"] += 1
        pState["timeStampTakeCareMonster"] = timestamp_now()

    elif cmd == Constant.CMD_NEXT_MONSTER:
        print("Monster Step reset and Monster Number increased.")
        pState = save["privateState"]
        pState["stepMonsterNumber"] = 0
        pState["monsterNumber"] += 1
        pState["timeStampTakeCareMonster"] = -1 # remove timer

    elif cmd == Constant.CMD_WIN_BONUS:
        coins = int(args[0])
        town_id = args[1]
        hero = int(args[2])
        claimId = int(args[3])
        cash = int(args[4])
        pState = save["privateState"]

        # CHE-4 replay protection: claimId must match the next expected id
        expected_id = pState.get("bonusNextId", 0)
        if claimId != expected_id:
            print(f"  WIN_BONUS rejected: claimId {claimId} != expected {expected_id}")
            return

        # CHE-4 rate limit: at least 30 min between claims
        now = timestamp_now()
        last = pState.get("timestampLastBonus", 0)
        if last and (now - last) < 30 * 60:
            print(f"  WIN_BONUS rejected: only {(now - last) // 60} min since last claim")
            return

        # CHE-4 value caps: align with MONDAY_BONUS_REWARDS magnitudes
        # (server has no authoritative table per-event, so cap generously)
        WIN_BONUS_MAX_CASH  = 10    # 2x Monday cash
        WIN_BONUS_MAX_COINS = 5000  # 2x Monday gold
        WIN_BONUS_MAX_HERO  = 1     # exactly 0 or 1 hero gift
        if cash < 0 or coins < 0 or hero < 0:
            print(f"  WIN_BONUS rejected: negative values")
            return
        if cash > WIN_BONUS_MAX_CASH:
            print(f"  WIN_BONUS cash capped: {cash} -> {WIN_BONUS_MAX_CASH}")
            cash = WIN_BONUS_MAX_CASH
        if coins > WIN_BONUS_MAX_COINS:
            print(f"  WIN_BONUS coins capped: {coins} -> {WIN_BONUS_MAX_COINS}")
            coins = WIN_BONUS_MAX_COINS
        if hero > WIN_BONUS_MAX_HERO:
            hero = WIN_BONUS_MAX_HERO

        print("Claiming Win Bonus")
        map = save["maps"][town_id]

        if cash != 0:
            save["playerInfo"]["cash"] = save["playerInfo"]["cash"] + cash
            print("Added " + str(cash) + " Cash to players balance")

        if coins != 0:
            map["coins"] = map["coins"] + coins
            print("Added " + str(coins) + " Gold to players balance")

        if hero != 0:
            length = len(save["privateState"]["gifts"])
            if length <= hero:
                for i in range(hero - length + 1):
                    save["privateState"]["gifts"].append(0)
            save["privateState"]["gifts"][hero] += 1
            print("Added Hero ID=" + str(hero))

        pState["bonusNextId"] = claimId + 1
        pState["timestampLastBonus"] = now

    elif cmd == Constant.CMD_COLLECT_MONDAY_BONUS:
        # Server enforces: only on Monday, and only once per 6 days.
        # Client-side button may show any day; server rejects silently otherwise.
        pState = save["privateState"]
        now = timestamp_now()
        last = pState.get("lastMondayBonusTs", 0)
        today_is_monday = datetime.date.today().weekday() == 0
        if not today_is_monday:
            print("  Monday bonus denied: not Monday")
            return
        if last and (now - last) < 6 * 24 * 3600:
            print(f"  Monday bonus denied: already claimed ({(now - last)//3600}h ago)")
            return
        rewards = get_game_config()["globals"].get("MONDAY_BONUS_REWARDS", [])
        units = get_game_config()["globals"].get("MONDAY_BONUS_UNITS", [])
        map = save["maps"][0]
        for r in rewards:
            rtype = r.get("type")
            value = int(r.get("value", 0))
            if rtype == "g":
                map["coins"] += value
            elif rtype == "c":
                save["playerInfo"]["cash"] += value
            elif rtype == "u":
                # Units: give the configured unit ids as gifts (from MONDAY_BONUS_UNITS).
                for unit_id in units:
                    uid = int(unit_id)
                    length = len(pState.get("gifts", []))
                    if length <= uid:
                        for _ in range(uid - length + 1):
                            pState.setdefault("gifts", []).append(0)
                    pState["gifts"][uid] += 1
        pState["lastMondayBonusTs"] = now
        print(f"  Monday bonus applied: {rewards}")

    elif cmd == Constant.CMD_COLLECT_COMEBACK_BONUS:
        # Comeback bonus: awarded when a player returns after a long absence.
        # Server enforces: only once per 30 days.
        pState = save["privateState"]
        now = timestamp_now()
        last = pState.get("lastComebackBonusTs", 0)
        if last and (now - last) < 30 * 24 * 3600:
            print(f"  Comeback bonus denied: already claimed ({(now - last)//3600}h ago)")
            return
        rewards = get_game_config()["globals"].get("COMEBACK_BONUS_REWARDS", [])
        units = get_game_config()["globals"].get("COMEBACK_BONUS_UNITS", [])
        map = save["maps"][0]
        for r in rewards:
            rtype = r.get("type")
            value = int(r.get("value", 0))
            if rtype == "g":
                map["coins"] += value
            elif rtype == "c":
                save["playerInfo"]["cash"] += value
            elif rtype == "u":
                for unit_id in units:
                    uid = int(unit_id)
                    length = len(pState.get("gifts", []))
                    if length <= uid:
                        for _ in range(uid - length + 1):
                            pState.setdefault("gifts", []).append(0)
                    pState["gifts"][uid] += 1
        pState["lastComebackBonusTs"] = now
        print(f"  Comeback bonus applied: {rewards}")

    elif cmd == Constant.CMD_ADMIN_ADD_ANIMAL:
        # CHE-1: Client-facing "admin" command disabled. Original would let any
        # client add arbitrary animals. Kept as no-op so the route doesn't log
        # "Unhandled command" noise, but grants nothing.
        print("  CMD_ADMIN_ADD_ANIMAL ignored (anti-cheat)")


    elif cmd == Constant.CMD_GRAVEYARD_BUY_POTIONS:
        # no args
        print("Graveyard buy potion")
        # info from config
        graveyard_potions = get_game_config()["globals"]["GRAVEYARD_POTIONS"]
        amount = graveyard_potions["amount"]
        price_cash = graveyard_potions["price"]["c"]
        # pay
        save["playerInfo"]["cash"] = max(int(save["playerInfo"]["cash"] - price_cash), 0)
        # add potion
        save["privateState"]["potion"] += amount

    elif cmd == Constant.CMD_RESURRECT_HERO:
        unit_id = args[0]
        x = args[1]
        y = args[2]
        town_id = args[3]
        bool_used_potion = len(args) > 4 and args[4] == '1'
        print("Resurrect", str(get_name_from_item_id(unit_id)), "from graveyard")
        map = save["maps"][town_id]
        # pay
        if bool_used_potion:
            quantity = 1
            save["privateState"]["potion"] = max(int(save["privateState"]["potion"] - quantity), 0)
        else:
            price_cash = get_game_config()["globals"]["GRAVEYARD_POTIONS"]["price"]["c"]
            save["playerInfo"]["cash"] = max(int(save["playerInfo"]["cash"] - price_cash), 0)
        # C.3: restore the level the unit had at CMD_KILL time (0 if no record).
        # hero_levels is consumed on resurrect so successive deaths don't double-grant.
        hero_levels = save["privateState"].get("hero_levels", {})
        level = int(hero_levels.pop(str(unit_id), 0))
        if level:
            print(f"  Restored level {level} from death record")
            save["privateState"]["hero_levels"] = hero_levels
        collected_at_timestamp = timestamp_now()
        orientation = 0
        map["items"] += [[unit_id, x, y, orientation, collected_at_timestamp, level]]

    elif cmd == Constant.CMD_BUY_SUPER_OFFER_PACK:
        town_id = args[0]
        unknown2 = args[1] # this is probably the super offer pack ID?
        items = args[2]
        cash_used = int(args[3])

        map = save["maps"][town_id]

        item_array = items.split(',')
        # CHE-9: enforce a floor of 10 cash per item so client can't pay 0 for a pack
        min_cost = max(10 * len(item_array), 10)
        if cash_used < min_cost:
            print(f"  Super offer pack: client sent {cash_used}, floored to {min_cost}")
            cash_used = min_cost

        for item in item_array:
            item_id = int(item)
            length = len(save["privateState"]["gifts"])
            if length <= item_id:
                for i in range(item_id - length + 1):
                    save["privateState"]["gifts"].append(0)
            save["privateState"]["gifts"][item_id] += 1

        save["playerInfo"]["cash"] = max(save["playerInfo"]["cash"] - cash_used, 0)
        print(f"Used {cash_used} cash to buy super offer pack ({len(item_array)} items)")

    elif cmd == Constant.CMD_SET_STRATEGY:
        strategy_type = args[0]
        type_name = get_strategy_type(strategy_type)
        save["privateState"]["strategy"] = strategy_type
        print(f"Set defense strategy type to {type_name}")

    elif cmd == Constant.CMD_START_QUEST:
        quest_id = args[0]
        town_id = args[1]
        print(f"Start quest {quest_id}")

    elif cmd == Constant.CMD_END_QUEST:
        try:
            data = json.loads(args[0])
        except (json.JSONDecodeError, TypeError) as e:
            print(f"CMD_END_QUEST: bad json: {e}")
            return
        town_id = data["map"]
        gold_gained = int(data["resources"]["g"])
        xp_gained = int(data["resources"]["x"])
        cash_gained = int(data["resources"].get("c", 0))
        units = data["units"]
        win = data["win"] == 1
        duration_sec = int(data.get("duration", 0))
        voluntary_end = data["voluntary_end"] == 1
        quest_id = int(data["quest_id"])
        item_rewards = data["item_rewards"] if "item_rewards" in data else None
        activators_left = data["activators_left"] if "activators_left" in data else None
        difficulty = data["difficulty"]

        # CHE-5 anti-cheat: cap rewards using MAX_*_QUEST from game config.
        # God difficulty is the highest tier (35000g / 8500 xp). Client-sent values
        # above those are rejected to the cap.
        globs = get_game_config()["globals"]
        MAX_GOLD = int(globs.get("MAX_GOLD_GOD_QUEST", 35000))
        MAX_XP = int(globs.get("MAX_XP_GOD_QUEST", 8500))
        MAX_CASH_PER_QUEST = 50
        MIN_QUEST_DURATION = 10  # seconds — prevents insta-win cheese
        if gold_gained < 0 or xp_gained < 0 or cash_gained < 0:
            print("CMD_END_QUEST rejected: negative rewards")
            return
        if duration_sec < MIN_QUEST_DURATION and win:
            print(f"CMD_END_QUEST: suspicious duration {duration_sec}s, zeroing rewards")
            gold_gained = xp_gained = cash_gained = 0
        if gold_gained > MAX_GOLD:
            print(f"CMD_END_QUEST: gold capped {gold_gained} -> {MAX_GOLD}")
            gold_gained = MAX_GOLD
        if xp_gained > MAX_XP:
            print(f"CMD_END_QUEST: xp capped {xp_gained} -> {MAX_XP}")
            xp_gained = MAX_XP
        if cash_gained > MAX_CASH_PER_QUEST:
            print(f"CMD_END_QUEST: cash capped {cash_gained} -> {MAX_CASH_PER_QUEST}")
            cash_gained = MAX_CASH_PER_QUEST

        # Resources
        save["maps"][town_id]["coins"] += gold_gained
        save["maps"][town_id]["xp"] += xp_gained
        if cash_gained > 0:
            save["playerInfo"]["cash"] += cash_gained
            print(f"  Quest cash reward: +{cash_gained}")

        # Update quests data
        save["privateState"]["unlockedQuestIndex"] = max(quest_id + 1, save["privateState"]["unlockedQuestIndex"], 0)
        # save["privateState"]["questsRank"] = TODO 
        # save["maps"]["questTimes"] [quest_id] = TODO min (... , duration_sec)
        # save["maps"]["lastQuestTimes"] [quest_id] = TODO min (... , duration_sec)

        print(f"Ended quest {quest_id}.")

    elif cmd == Constant.CMD_ADD_COLLECTABLE:
        collection_id = args[0]
        collectible_id = args[1]
        # TODO

    elif cmd == Constant.CMD_ACTIVATE:
        # User clicks "activate" on a production building (mine/mill/farm)
        # to start (or reset) its production cycle. The SWF sends:
        #   [x, y, town_id, item_id, frame]
        # where `frame` is a visual state marker (4 is what we've seen for
        # the first-activation state). The server needs to reset
        # item[4] (collected_at_timestamp) so the client's countdown
        # starts now, and persist the frame so next page load re-renders
        # the building in its activated state.
        # Without this handler the mine looks active on-screen but is
        # silently not tracked in the save — after a logout/login the
        # player sees it idle again ("minas não estão mais trabalhando").
        x = args[0]
        y = args[1]
        town_id = args[2]
        item_id = args[3]
        frame = args[4] if len(args) > 4 else 0
        print(f"Activate {get_name_from_item_id(item_id)} at ({x},{y}), frame={frame}")
        map = save["maps"][town_id]
        for item in map["items"]:
            if item[0] == item_id and item[1] == x and item[2] == y:
                if len(item) > 3:
                    item[3] = frame
                if len(item) > 4:
                    item[4] = timestamp_now()
                break

    else:
        # Shape-revealing log: UNHANDLED <cmd> [<num_args>]: <json-of-args>
        # easy to grep in `docker logs ... | grep "UNHANDLED "`.
        try:
            args_preview = json.dumps(args)[:500]
        except Exception:
            args_preview = repr(args)[:500]
        print(f"UNHANDLED {cmd!r} [{len(args) if hasattr(args, '__len__') else '?'}]: {args_preview}")
        return
    
