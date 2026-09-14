# Changelog

All notable changes to `get-haiggoh` are documented in this file.

## [Unreleased]

## [0.5.0] - 2026-09-15

### Added
- Added `--help` support to `get-haiggoh.py` for proper usage information
- Added `get-haiggoh-menu` - a menu-driven interface for managing plugins
- Default action in menu is to install/update all plugins (press Enter or choose 2)
- Menu provides options to plan/apply all plugins or specific plugins (by name/category)

### Fixed
- Fixed `get-haiggoh.py` to show usage when called without valid arguments instead of exiting silently
- Maintained backward compatibility with existing usage patterns

### Documentation
- Updated README.md with comprehensive usage instructions for both direct and menu-driven interfaces
- Added examples for interactive menu usage