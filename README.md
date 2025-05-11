# scc-lan-restore

[README](README.md) | [中文文档](README_zh.md)

Restores LAN mode on Splinter Cell Conviction after servers shutdown.

# UPDATES

- 09/01/2025: v3 update instruction and script, discovering and joining Lan sessions is more stable. Also add detailed logs (also come in chinese version) to help troubleshooting. please update script. 
- 03/01/2024: v2 includes important fixes for "Unable to Join the Match. The connection is not responding", please update script.
- 05/01/2024: added [windows executable](https://github.com/Ododo/scc-lan-restore/releases/) as alternative to installing python.

# Current Status
[NEED TESTING]

1. ByPassed LAN menu blocked with error message "The Splinter Cell Conviction server is not available at this time, please try again later." [**OK**]

2. Able to discover and host Lan sessions [**OK**]

3. Able to Join a session [**OK**]

4. Play the Game [**OK**]  
The fix appears to work for most people.

5. Out-of-sync or remote client disconnected issues.  
This is an issue not related to the lan restore fix, but i'm doing some investigations nevertheless.
The problematic code was identified but not fully understood, i will maybe write somewhere what i collected
so far.  
Legend says it is related to running AMD Ryzen versus Intel CPUs or older AMD cpus.

# Instructions
Windows 10/11, tested on Windows 10 and 11.
1. Set the preferred network interface used by game. If you don't see other sessions when searching for games, it is likely that the outgoing broadcast packet searching for lan sessions is sent via the wrong interface, messing up with the session discovery. You can verify what IP address the game is using by checking the logs printed. (e.g. "Game will likely use IP x.x.x.x" after run script, and "Send packet: game broadcast search packet using x.x.x.x" on searching for sessions in game). 

    To set the network interface priority (as shown in the image below):
    1. Press `Win + R` keys to open Run, type **ncpa.cpl** and press enter to open Network Connections.
    2. Right click on the network adapter (e.g.: "Radmin VPN") you want to change the priority for, this usually is the virtual interface created by your "VPN" system like Radmin VPN to play with remote players, or the physical interface like "Ethernet x" if you are playing on physical LAN network. And click **Properties**.
    3. Select **Internet Protocol Version 4 (TCP/IPv4)**, and click **Properties**.
    4. Click **Advanced**.
    5. Uncheck the **Automatic metric** box, enter **1** in **Interface metric**, the smaller the more priority, then click **OK**.
      
       ![](src/priority.png)
    
   **Note**: If this does not take effect, you should make sure other interfaces' metric has checked "automatic" or set to a larger value, it is known that radmin sets its metric to 1. (Or just deactivate all unused network interfaces) 

2. You will need to edit *C:\Windows\System32\drivers\etc\hosts* and add `127.0.0.1 gconnect.ubi.com` at the bottom. Then open powershell and type `ipconfig /flushdns`  

    What it does is that it will tell the game to look for 127.0.0.1 when it is trying to connect to gconnect.ubi.com. We will handle instead the request from the game as 127.0.0.1 is our local machine.

    The game used to request some configuration from gconnect.ubi.com on port 3074, but this service is now on port 80. Serving from localhost is more futureproof as we don't rely on external services.

    This is what actually blocked the LAN menu.

3. The workaround currently relies on a Python script. You can either run it from Python following theses steps below, or run directly as administator the [executable](https://github.com/Ododo/scc-lan-restore/releases/) created with pyinstaller.
   * Install Python3 preferably from [https://www.python.org/](https://www.python.org/downloads/windows/), check "Add Python to PATH", select "Customize installation" and check "[pip](https://pip.pypa.io/en/stable/installation/)".
   * Install pip package pydivert `pip install pydivert` or `python -m pip install pydivert`
   * Download scc_lan_helper.py from this repository.
   * Then open Windows terminal or powershell *as administrator*, and run the service with
     `python scc_lan_helper.py` and that's it.
   
   **You will need to keep the program window open while playing the game.** You can run the program at any time without having to restart the game, all changes take effect immediately.

# What does the python script do and why do i need to run as administrator
  The administrator privileges are required because the script relies on hooking some inbound UDP packets used by the game and modifying them before they are handled by the game.

  There are 2 parts: 1) A socket server listening on port 3074 and answering the game HTTP requests. 2) The hook part which aims to fix the UDP discovery reply sent by the game host telling "i'm currently hosting a game, and those are the infos to connect". It will edit the packets so that your game client will be able to join.

  When running the script, some helpful logs will be printed to help debugging. For example, if you can't find or join another session, check if you and your friend's IP address used by the game are mutually reachable. (Usually IPs of the same subnet like 192.168.1.x are reachable. Keyword to search for is *route table*.)


# Test results, troubleshooting
General protection faults on Windows 10, possible solutions:
- Install [Virtual Audio Cable](https://vb-audio.com/Cable/) (reported working on https://github.com/Ododo/scc-lan-restore/issues/2)
- Plug in both microphone and headphones
- Try this guide: https://steamcommunity.com/sharedfiles/filedetails/?id=271381800
- Use legal copy of the game (Steam, ubisoft,...)
- Upgrade to Windows 11

# Known Issues

Pydivert causes outbound broadcast packet to be duplicated, so multiple session may appear in game, you can safely choose any one of them.

Please open issues here, thanks.

# Detailed explanation for advanced users

What game does:
1. host create session
2. client send search packet: send udp broadcast packet to 255.255.255.255:46000, payload len == 54
3. host respond with session info packet: send udp broadcast packet to 255.255.255.255:46000, payload len > 500, which (should) contain host's ip and mac address.
4. client try to directly communicate with host (udp port 9103 on both machine), using ip in host's info packet.

What could go wrong:
1. Packet sent from the wrong interface if multiple interfaces are activated.
   
   This will cause packets not able to reach the other machine, causing client unable to find host session.

   The game send packets using interface whose route to 255.255.255.255 has the smallest *metric*, you can check route table by running `route print` in cmd / powershell. Look for lines whose *Network Address* is 255.255.255.255, if metric (the last column) is the smallest, that interface will be used. Any changes made to route table (like step 1 of instruction section) takes effect immediately without having to restart the game or this tool.

2. Host's ip information in session info packet is wrong.
   
   The ip field in the session info packet's payload is of variable length, it may contain all ip addresses of the active interfaces on host's machine. Sometimes for unknown reason, the ip field is empty. Both cases would cause trouble, in the first case, client might try to connect to the unexpected ip address, in the second case, the client don't known how to reach the host. That's why even client can see host session (i.e. client can receive the host's packet), but fail to connect to it (i.e. wrong information provided in the packet's payload).

   To fix this, we read the real ip where the packet is received from (this is definitely correct or you will not receive it in the first place), and simply replace the original ip field in the packet (no matter empty or more than one) with this ip.


