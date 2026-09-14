# get-haiggoh

CLI tool to manage haiggoh plugins for Claude Code.

## Usage

### Direct Usage
```bash
# See what would be installed/updated (dry run)
./bin/get-haiggoh.py plan

# Actually install/update plugins
./bin/get-haiggoh.py apply

# Limit to specific plugins
./bin/get-haiggoh.py plan --only video-use,waypoints
./bin/get-haiggoh.py apply --only video-use,waypoints

# Limit to specific category
./bin/get-haiggoh.py plan --category utility
./bin/get-haiggoh.py apply --category utility

# Show help
./bin/get-haiggoh.py --help
```

### Menu-Driven Usage
For an interactive menu experience:
```bash
./bin/get-haiggoh-menu
```

The menu-driven interface provides:
- **Default action** (press Enter or choose 2) is to install/update all plugins
- Option 1: Plan all plugins (dry run)
- Option 2: Apply all plugins (install/update) [DEFAULT]
- Option 3: Plan specific plugins (by name or category)
- Option 4: Apply specific plugins (by name or category)
- Option 5: Exit

When choosing specific plugin options, you can enter:
- `--only name1,name2` to limit to specific plugins
- `--category NAME` to limit to plugins in a specific category
- Leave empty (just press Enter) to operate on all plugins

## Examples
```bash
# Interactive menu - install/update all plugins (default)
./bin/get-haiggoh-menu
# Just press Enter at the menu

# Interactive menu - plan specific plugins
./bin/get-haiggoh-menu
# Choose option 3, then enter: --only video-use,waypoints

# Interactive menu - apply updates to utility category
./bin/get-haiggoh-menu
# Choose option 4, then enter: --category utility
```

## Installation
This tool is typically installed as part of the get-haiggoh package. The scripts are located in the `bin/` directory:

- `bin/get-haiggoh.py` - Direct command-line interface
- `bin/get-haiggoh-menu` - Menu-driven interface

Both scripts are designed to be run from the repository root or via their absolute paths.