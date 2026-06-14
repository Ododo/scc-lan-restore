import threading

from find_interface_priority import find_broadcast_priority
from bypass_server_check import server_check_hook
from log import logger_zh, logger_en
import sys

if __name__ == "__main__":
    # find the ip address that the game will likely use
    priority_ip = find_broadcast_priority()
    if priority_ip:
        logger_zh.info(
            f'预计游戏将使用IP: "{priority_ip}" (仅供参考，实际IP以后续抓包日志为准)\n'
        )
        logger_en.info(
            f'Game will likely use IP: "{priority_ip}" (for reference only, check later logs for real IP)\n'
        )
    else:
        logger_zh.info("预估游戏使用的IP失败，请以实际日志为准\n")
        logger_en.info(
            "Failed to find what IP the game will likely use, check later logs for real IP\n"
        )

    # start lan packet fixing thread
    if sys.platform.startswith("linux"):
        from fix_lan_packet_linux import linux_packet_hook
        hook_thread = threading.Thread(target=linux_packet_hook)
        hook_thread.start()
    elif sys.platform.startswith("win"):
        from fix_lan_packet import packet_hook
        hook_thread = threading.Thread(target=packet_hook)
        hook_thread.start()

    # start server bypass
    server_check_hook()
