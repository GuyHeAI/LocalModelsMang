#!/usr/bin/env python3
import argparse
import json
import os
import urllib.request

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REGISTRY_FILE = os.path.join(_SCRIPT_DIR, ".claude", "models_registry.json")
SETTINGS_FILE = os.path.join(_SCRIPT_DIR, ".claude", "settings.json")

def load_registry():
    if not os.path.exists(REGISTRY_FILE):
        return {}
    with open(REGISTRY_FILE, 'r') as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return {}

def save_registry(registry):
    os.makedirs(os.path.dirname(REGISTRY_FILE), exist_ok=True)
    with open(REGISTRY_FILE, 'w') as f:
        json.dump(registry, f, indent=4)

def load_settings():
    if not os.path.exists(SETTINGS_FILE):
        return {"env": {}, "model": ""}
    with open(SETTINGS_FILE, 'r') as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return {"env": {}, "model": ""}

def save_settings(settings):
    os.makedirs(os.path.dirname(SETTINGS_FILE), exist_ok=True)
    with open(SETTINGS_FILE, 'w') as f:
        json.dump(settings, f, indent=4)

def cmd_list(registry):
    if not registry:
        print("No models registered.")
        return

    try:
        settings = load_settings()
        active_model_id = settings.get("model", "")
        active_url = settings.get("env", {}).get("ANTHROPIC_BASE_URL", "")
    except Exception:
        active_model_id = ""
        active_url = ""

    print(f"{'NAME / MODEL ID':<45} {'BASE URL':<30}")
    print("-" * 75)
    for name, config in registry.items():
        is_active = (config['model_id'] == active_model_id and
                     config.get('base_url', '') == active_url)
        prefix = "[*] " if is_active else "    "

        m_id = str(config['model_id'])
        b_url = str(config.get('base_url') if config.get('base_url') else 'N/A')

        # Merge columns if name and model_id are identical to avoid redundancy
        display_name = f"{name} ({m_id})" if name != m_id else name

        print(f"{prefix}{display_name:<42} {b_url:<30}")

def cmd_add(registry, name, model_id, base_url):
    registry[name] = {"model_id": model_id, "base_url": base_url or None}
    save_registry(registry)
    print(f"Added model '{name}'.")

def cmd_remove(registry, name):
    if name in registry:
        del registry[name]
        save_registry(registry)
        print(f"Removed model '{name}'.")
    else:
        print(f"Error: Model '{name}' not found.")

def cmd_use(registry, name):
    if name not in registry:
        print(f"Error: Model '{name}' not found.")
        return

    config = registry[name]
    settings = load_settings()

    settings["model"] = config['model_id']

    if config.get('base_url'):
        if "env" not in settings:
            settings["env"] = {}
        # Strip trailing /v1 to prevent duplication if Claude Code appends it
        url = config['base_url'].rstrip('/')
        if url.endswith('/v1'):
            url = url[:-3]
        settings["env"]["ANTHROPIC_BASE_URL"] = url
    else:
        if "env" in settings and "ANTHROPIC_BASE_URL" in settings["env"]:
            del settings["env"]["ANTHROPIC_BASE_URL"]

    save_settings(settings)
    print(f"Switched to model '{name}' ({config['model_id']}).")

def cmd_sync(registry, base_url):
    """Sync models from an OpenAI-compatible /v1/models endpoint."""
    # Ensure we have the correct URL for fetching models
    fetch_url = base_url.rstrip('/')
    if not fetch_url.endswith('/v1'):
        fetch_url += '/v1'

    models_api_url = f"{fetch_url}/models"
    print(f"Syncing models from {models_api_url}...")

    try:
        with urllib.request.urlopen(models_api_url) as response:
            data = json.loads(response.read().decode('utf-8'))

        active_ids = {model_info['id'] for model_info in data.get('data', [])}
        target_base_url = fetch_url.rstrip('/v1')

        new_models_found = 0
        removed_models_count = 0

        # Identify models to add
        for model_id in active_ids:
            if model_id not in registry:
                registry[model_id] = {"model_id": model_id, "base_url": target_base_url}
                new_models_found += 1

        # Identify models to remove (only those that belong to this server)
        to_remove = []
        for name, config in registry.items():
            if config.get('base_url') == target_base_url:
                if config['model_id'] not in active_ids:
                    to_remove.append(name)

        for name in to_remove:
            del registry[name]
            removed_models_count += 1

        if new_models_found > 0 or removed_models_count > 0:
            save_registry(registry)
            msg = f"Sync complete. Added {new_models_found}, Removed {removed_models_count}."
            print(msg)
        else:
            print("No changes needed.")

    except Exception as e:
        print(f"Error syncing models: {e}")

def main():
    parser = argparse.ArgumentParser(description="Claude Code Model Manager")
    subparsers = parser.add_subparsers(dest="command", help="Commands")

    subparsers.add_parser("list", help="List all registered models")

    add_parser = subparsers.add_parser("add", help="Add a new model")
    add_parser.add_argument("name", help="Name for the model")
    add_parser.add_argument("model_id", help="Model identifier (e.g., claude-3-5-sonnet)")
    add_parser.add_argument("--url", help="Base URL for local models (optional)", default=None)

    remove_parser = subparsers.add_parser("remove", help="Remove a model")
    remove_parser.add_argument("name", help="Name of the model to remove")

    use_parser = subparsers.add_parser("use", help="Switch to a model")
    use_parser.add_argument("name", help="Name of the model to use")

    sync_parser = subparsers.add_parser("sync", help="Sync models from an OpenAI-compatible server")
    sync_parser.add_argument("url", help="The base URL of the server (e.exp: http://127.0.0.1:1234/v1)")

    args = parser.parse_args()
    registry = load_registry()

    if args.command == "list":
        cmd_list(registry)
    elif args.command == "add":
        cmd_add(registry, args.name, args.model_id, args.url)
    elif args.command == "remove":
        cmd_remove(registry, args.name)
    elif args.command == "use":
        cmd_use(registry, args.name)
    elif args.command == "sync":
        cmd_sync(registry, args.url)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
