# scc-lan-restore
Aims to restore the ability to play LAN mode on Splinter Cell Conviction after servers shutdown.

# Current Status
[NEED TESTING]

1. ByPassed LAN menu blocked with error message "The Splinter Cell Conviction server is not available at this time, please try again later." [**OK**]

2. Able to discover Lan sessions [**OK**]

3. Able to Join a session [**OK**]

4. Play the Game

I was able to start a match with 2 PCs at Home, However i'm getting out of sync or
remote client disconnected.
It might be because one of my PCs is very weak compared to the other and struggles to run the game.
This is why i need other people to test this workaround

# Instructions
Windows 10/11, tested on Windows 11 only. 

1. In order to prevent some issue like you don't see other sessions when searching for games,
   You will probably need to deactivate all **virtual** internet interfaces like the one from VirtualBox or Hyper-v. The problem is that the outgoing multicast packets to search for lan sessions might be routed to the wrong interfaces, messing up with the session discovery. Of course if you are using a "VPN" system like Radmin VPN to play with remote players, you should keep active the virtual interface it creates in windows, as the packets are intended to go through this interface.

2. You will need to edit *C:\Windows\System32\drivers\etc\hosts* and add `127.0.0.1 gconnect.ubi.com` at the bottom. Then open powershell and type `> ipconfig /flushdns`  
  What it does is that it will tell the game to look for 127.0.0.1 when it is trying to connect to gconnect.ubi.com. We will handle instead the request from the game as 127.0.0.1 is our local machine.
The game used to request some configuration from gconnect.ubi.com on port 3074, but this service is no longer active (altough it is still active but now on port 80 :D... But serving from localhost is more futureproof as we don't rely on external services.). This is what actually blocked the LAN menu.

4. The workaround currently relies on a python script.
   * Install Python3 (with windows store for example) along with pip https://pip.pypa.io/en/stable/installation/,
   * Install pip package pydivert `python3 -m pip install pydivert`
   * Download scc_lan_helper.py from this repository.
   * Then open Windows terminal or powershell *as administrator*, and run the service with
   `> python scc_lan_helper.py` and that's it..
   **You will need to keep this powershell window open whil playing the game.**

# What does the python script do and why do i need to run as administrator
  The administrator priviliedges are required because the script relies on hooking UDP packets used by the game and modifying them before they are sent through the interface and to the LAN.
  There are 2 parts: a socket server listening on port 3074 and answering the game HTTP requests.
  The hook part which aims to fix the UDP discovery reply sent by the game host telling "i'm currently hosting a game, and those are the infos to connect". It will edit the packets so that your game client will be able to join.

# Test results, troubleshooting
Please open issues here, thanks.
