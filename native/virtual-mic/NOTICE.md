# Third-party source and local changes

The `internal/` packages and their tests are from Virtual Cables by Tarek Wasfy and AI:
https://github.com/tarekwasfy01/Virtual-Cables/tree/8a819c29971d30a73955178ac8a3aac00b1a5230/src/internal

Upstream commit: `8a819c29971d30a73955178ac8a3aac00b1a5230`.
License: BSD-2-Clause, reproduced in LICENSE. Original copyright retained.

Local changes: product, manufacturer, and serial strings identify Speak Sound;
the new MIT-licensed `cmd/speak-sound-mic/main.go` hosts one device only on
127.0.0.1:32401 and exits on its parent's stdin closing. It has no installer or GUI.
Experimental USB VID/PID values come from upstream and are not registered hardware IDs.

Audio is 48 kHz, stereo, 16-bit PCM. The ring capacity is 80 ms, not a measured
end-to-end latency. Windows supplies its USB Audio Class driver. The open-source
USB/IP transport (usbip-win2, BSD-2-Clause) must be separately installed from a
Microsoft-signed release; no new custom audio kernel driver is included here.

This is an experimental USB emulation backend. Do not claim game/anti-cheat
compatibility without testing. No secure-boot, code-integrity, or certificate
store changes are needed or made by this program.
