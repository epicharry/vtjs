import os
import json
import base64
import requests

requests.packages.urllib3.disable_warnings()

CLIENT_PLATFORM = "ew0KCSJwbGF0Zm9ybVR5cGUiOiAiUEMiLA0KCSJwbGF0Zm9ybU9TIjogIldpbmRvd3MiLA0KCSJwbGF0Zm9ybU9TVmVyc2lvbiI6ICIxMC4wLjE5MDQyLjEuMjU2LjY0Yml0IiwNCgkicGxhdGZvcm1DaGlwc2V0IjogIlVua25vd24iDQp9"
CLIENT_VERSION = "release-11.02-25-3708969"
DEFAULT_REGION = "ap"

def fetch_tokens():
    """Fetch authentication tokens from Riot Client lockfile"""
    lockfile_path = os.path.join(os.getenv('LOCALAPPDATA'), "Riot Games", "Riot Client", "Config", "lockfile")
    with open(lockfile_path, "r") as f:
        name, pid, port, password, protocol = f.read().split(":")
    auth_header = base64.b64encode(f"riot:{password}".encode()).decode()
    base_url = f"{protocol}://127.0.0.1:{port}"
    r = requests.get(f"{base_url}/entitlements/v1/token",
                     headers={"Authorization": f"Basic {auth_header}"}, verify=False)
    tokens = r.json()
    auth_token = tokens["accessToken"]
    ent_token = tokens["token"]
    puuid = json.loads(base64.b64decode(auth_token.split('.')[1] + "=="))["sub"]
    return auth_token, ent_token, puuid

def resolve_shard(auth_token, ent_token, puuid):
    """Resolve the player's shard/region"""
    url = f"https://pd.{DEFAULT_REGION}.a.pvp.net/name-service/v2/players"
    headers = {
        "Authorization": f"Bearer {auth_token}",
        "X-Riot-Entitlements-JWT": ent_token,
        "X-Riot-ClientPlatform": CLIENT_PLATFORM,
        "X-Riot-ClientVersion": CLIENT_VERSION,
        "Content-Type": "application/json"
    }
    response = requests.put(url, headers=headers, json=[puuid], verify=False)
    data = response.json()
    if isinstance(data, list) and len(data) > 0:
        return data[0].get("Shard", DEFAULT_REGION)
    return DEFAULT_REGION

def get_player_mmr(auth_token, ent_token, puuid, shard):
    """Fetch player MMR data including all seasonal information"""
    url = f"https://pd.{shard}.a.pvp.net/mmr/v1/players/{puuid}"
    headers = {
        "Authorization": f"Bearer {auth_token}",
        "X-Riot-Entitlements-JWT": ent_token,
        "X-Riot-ClientPlatform": CLIENT_PLATFORM,
        "X-Riot-ClientVersion": CLIENT_VERSION
    }
    
    response = requests.get(url, headers=headers, verify=False)
    return response.json(), response.text

def calculate_peak_rank(mmr_data):
    """Calculate peak rank from MMR data using the same logic as VTJS"""
    queue_skills = mmr_data.get("QueueSkills", {})
    competitive = queue_skills.get("competitive", {})
    seasonal_info = competitive.get("SeasonalInfoBySeasonID", {})
    
    if not seasonal_info:
        return {
            "peak_rank_tier": 0,
            "peak_rank_name": "UNRANKED",
            "peak_season_id": None,
            "current_rank_tier": 0,
            "current_rr": 0,
            "last_game_mmr_diff": 0
        }
    
    # Find peak rank across all seasons
    seasons = list(seasonal_info.values())
    peak_season = max(seasons, key=lambda x: x.get("CompetitiveTier", 0))
    
    # Get current rank info
    latest_update = mmr_data.get("LatestCompetitiveUpdate", {})
    
    return {
        "peak_rank_tier": peak_season.get("CompetitiveTier", 0),
        "peak_season_id": peak_season.get("SeasonID"),
        "peak_season_wins": peak_season.get("NumberOfWins", 0),
        "peak_season_games": peak_season.get("NumberOfGames", 0),
        "current_rank_tier": latest_update.get("TierAfterUpdate", 0),
        "current_rr": latest_update.get("RankedRatingAfterUpdate", 0),
        "last_game_mmr_diff": latest_update.get("RankedRatingEarned", 0),
        "all_seasons": seasonal_info
    }

def get_rank_name(tier):
    """Convert rank tier number to readable name"""
    rank_names = {
        0: "UNRANKED",
        3: "IRON 1", 4: "IRON 2", 5: "IRON 3",
        6: "BRONZE 1", 7: "BRONZE 2", 8: "BRONZE 3",
        9: "SILVER 1", 10: "SILVER 2", 11: "SILVER 3",
        12: "GOLD 1", 13: "GOLD 2", 14: "GOLD 3",
        15: "PLATINUM 1", 16: "PLATINUM 2", 17: "PLATINUM 3",
        18: "DIAMOND 1", 19: "DIAMOND 2", 20: "DIAMOND 3",
        21: "ASCENDANT 1", 22: "ASCENDANT 2", 23: "ASCENDANT 3",
        24: "IMMORTAL 1", 25: "IMMORTAL 2", 26: "IMMORTAL 3",
        27: "RADIANT"
    }
    return rank_names.get(tier, f"UNKNOWN_TIER_{tier}")

def display_peak_rank_info(peak_info):
    """Display formatted peak rank information"""
    print("\nPeak Rank Information:")
    print("=" * 50)
    print(f"Peak Rank: {get_rank_name(peak_info['peak_rank_tier'])}")
    print(f"Peak Rank Tier: {peak_info['peak_rank_tier']}")
    print(f"Peak Season ID: {peak_info['peak_season_id']}")
    print(f"Peak Season Wins: {peak_info['peak_season_wins']}")
    print(f"Peak Season Games: {peak_info['peak_season_games']}")
    
    if peak_info['peak_season_games'] > 0:
        winrate = (peak_info['peak_season_wins'] / peak_info['peak_season_games']) * 100
        print(f"Peak Season Winrate: {winrate:.1f}%")
    
    print("\nCurrent Rank Information:")
    print("-" * 30)
    print(f"Current Rank: {get_rank_name(peak_info['current_rank_tier'])}")
    print(f"Current RR: {peak_info['current_rr']}")
    print(f"Last Game MMR Change: {peak_info['last_game_mmr_diff']:+d}")
    
    print(f"\nAll Seasons Summary:")
    print("-" * 30)
    for season_id, season_data in peak_info['all_seasons'].items():
        tier = season_data.get('CompetitiveTier', 0)
        wins = season_data.get('NumberOfWins', 0)
        games = season_data.get('NumberOfGames', 0)
        print(f"Season {season_id[:8]}...: {get_rank_name(tier)} ({wins}W/{games}G)")

if __name__ == "__main__":
    try:
        print("Valorant Peak Rank Fetcher")
        print("=" * 40)
        
        # Fetch authentication tokens
        print("Fetching authentication tokens...")
        auth_token, ent_token, local_puuid = fetch_tokens()
        
        # Resolve shard
        print("Resolving shard...")
        shard = resolve_shard(auth_token, ent_token, local_puuid)
        print(f"Using shard: {shard}")
        
        # Get target PUUID
        target_puuid = input("\nEnter the target player's PUUID (or press Enter to use your own): ").strip()
        if not target_puuid:
            target_puuid = local_puuid
            print(f"Using your PUUID: {target_puuid}")
        
        # Fetch MMR data
        print("\nFetching player MMR data...")
        mmr_data, raw_mmr_response = get_player_mmr(auth_token, ent_token, target_puuid, shard)
        
        # Calculate peak rank
        peak_info = calculate_peak_rank(mmr_data)
        
        # Display results
        display_peak_rank_info(peak_info)
        
        # Save responses to files
        filename_base = f"peak_rank_{target_puuid}"
        
        # Save raw MMR response
        with open(f"{filename_base}_raw.json", "w") as f:
            f.write(raw_mmr_response)
        
        # Save processed peak rank data
        with open(f"{filename_base}_processed.json", "w", encoding='utf-8') as f:
            json.dump({
                "puuid": target_puuid,
                "shard": shard,
                "peak_rank_info": peak_info,
                "timestamp": mmr_data.get("Version", 0)
            }, f, indent=2, ensure_ascii=False)
        
        print(f"\nData saved to:")
        print(f"- {filename_base}_raw.json (Raw API response)")
        print(f"- {filename_base}_processed.json (Processed peak rank data)")
        
    except FileNotFoundError:
        print("Error: Could not find Riot Client lockfile.")
        print("Make sure the Riot Client is running and you're logged in.")
    except requests.exceptions.RequestException as e:
        print(f"Network error: {e}")
    except json.JSONDecodeError as e:
        print(f"JSON parsing error: {e}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        print("Make sure the Riot Client is running and you're logged in.")