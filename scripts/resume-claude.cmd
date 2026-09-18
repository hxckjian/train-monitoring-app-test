@echo off
rem Double-click launcher: resumes the Claude Code session in its project folder.
rem Edit the two values in resume-claude.ps1, or pass them here:
rem   resume-claude.cmd "C:\path\to\project" <session-id>
powershell -NoExit -ExecutionPolicy Bypass -File "%~dp0resume-claude.ps1" %*
