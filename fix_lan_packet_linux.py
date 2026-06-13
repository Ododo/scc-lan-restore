"""
Linux port of fix_lan_packet.py from scc-lan-restore
Uses nfqueue (netfilter) instead of pydivert (Windows-only)

Requirements:
    pip install scapy NetfilterQueue

Before running, set up iptables rules:
    sudo iptables -I INPUT  -p udp --dport 46000 -j NFQUEUE --queue-num 0
    sudo iptables -I OUTPUT -p udp --dport 46000 -j NFQUEUE --queue-num 0

To remove rules after playing:
    sudo iptables -D INPUT  -p udp --dport 46000 -j NFQUEUE --queue-num 0
    sudo iptables -D OUTPUT -p udp --dport 46000 -j NFQUEUE --queue-num 0

Run as root: sudo python fix_lan_packet_linux.py
"""

import socket
import datetime
from netfilterqueue import NetfilterQueue
from scapy.all import IP, UDP, Raw
from log import logger_zh, logger_en


def get_timestamp():
    return datetime.datetime.now().strftime("%H:%M:%S")


def fix_packet(pkt):
    """Called by nfqueue for every matching packet."""

    raw = pkt.get_payload()
    scapy_pkt = IP(raw)

    if not scapy_pkt.haslayer(UDP):
        pkt.accept()
        return

    udp = scapy_pkt[UDP]
    payload = bytes(udp.payload)
    src_addr = scapy_pkt[IP].src
    dst_addr = scapy_pkt[IP].dst

    is_inbound = dst_addr != "255.255.255.255" and dst_addr == get_local_ip()
    is_outbound = dst_addr == "255.255.255.255"

    is_search_packet = len(payload) == 54
    is_hostinfo_packet = len(payload) > 500

    print(f"[{get_timestamp()}]")

    if is_inbound and is_search_packet:
        logger_zh.info(f"收到数据包：\n来自客户端（队友） {src_addr} 的房间搜索请求\n")
        logger_en.info(
            f"Receive packet: client (your partner)'s search request from {src_addr}\n"
        )
    elif is_outbound and is_search_packet:
        logger_zh.info(f"发送数据包：\n游戏从 {src_addr} 广播发出房间搜索数据包\n")
        logger_en.info(f"Send packet: game broadcast search packet using {src_addr}\n")
    elif is_inbound and is_hostinfo_packet:
        logger_zh.info(f"收到数据包：\n来自房主（队友） {src_addr} 的房间信息数据包\n")
        logger_en.info(
            f"Receive packet: host (your partner)'s info packet from {src_addr}\n"
        )
    elif is_outbound and is_hostinfo_packet:
        logger_zh.info(
            f"发送数据包：\n游戏从 {src_addr} 广播发出房间信息数据包（给队友）\n"
        )
        logger_en.info(
            f"Send packet: game broadcast host info packet (to your partner) using {src_addr}\n"
        )

    # Only modify inbound host info packets
    if is_inbound and is_hostinfo_packet:
        payload = bytearray(payload)

        partner_ip = src_addr
        # ip field format: 07 <4-byte ip> 05 23 8F
        ip_bytes = socket.inet_aton(partner_ip)
        partner_ip_field = (
            bytearray(b"\x07") + bytearray(ip_bytes) + bytearray(b"\x05\x23\x8f")
        )

        num_available_ips = payload[0x5B] - 1

        if num_available_ips == 0:
            # Insert ip field if empty
            payload = payload[:0x5C] + partner_ip_field + payload[0x5C:]
        elif num_available_ips >= 2:
            # Remove extra ip fields
            payload = (
                payload[:0x5C]
                + partner_ip_field
                + payload[0x5C + len(partner_ip_field) * num_available_ips :]
            )
        else:
            # Update existing ip field
            payload[0x5C : 0x5C + len(partner_ip_field)] = partner_ip_field

        payload[0x5B] = 2  # 1 ip + 1

        logger_zh.info(f"将房间信息中的房主IP改为: {partner_ip}\n")
        logger_en.info(f"Change host IP in info packet to: {partner_ip}\n")

        # Rebuild scapy packet with modified payload
        scapy_pkt[UDP].remove_payload()
        scapy_pkt = scapy_pkt / Raw(load=bytes(payload))

        # Recalculate checksums
        del scapy_pkt[IP].chksum
        del scapy_pkt[UDP].chksum
        scapy_pkt = IP(bytes(scapy_pkt))

        pkt.set_payload(bytes(scapy_pkt))

        logger_zh.info("数据包已转发给游戏！")
        logger_en.info("Packet forwarded to game!")
    else:
        if is_outbound:
            logger_zh.info("数据包已转发给网卡。")
            logger_en.info("Packet forwarded to network adapter.")

    print("\n")
    pkt.accept()


def get_local_ip():
    """Get the local IP used for LAN traffic."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("192.168.1.1", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def linux_packet_hook():
    logger_zh.info(
        "开始对搜索房间、加入房间等行为进行抓包，请确认后续日志中的ip地址是否正确，如需修改游戏使用的网卡，请参考README\n"
    )
    logger_en.info(
        "Start monitoring packets for searching for and connecting to sessions, please check if ip address is correct in later logs, and refer to README to change the preferred network interface\n"
    )

    logger_zh.info(f"检测到本地 IP 为: {get_local_ip()}\n")
    logger_en.info(f"Local IP detected as: {get_local_ip()}\n")

    logger_zh.info(
        "请确保已设置 iptables 规则：\n  sudo iptables -I INPUT  -p udp --dport 46000 -j NFQUEUE --queue-num 0\n  sudo iptables -I OUTPUT -p udp --dport 46000 -j NFQUEUE --queue-num 0\n"
    )
    logger_en.info(
        "Make sure iptables rules are set:\n  sudo iptables -I INPUT  -p udp --dport 46000 -j NFQUEUE --queue-num 0\n  sudo iptables -I OUTPUT -p udp --dport 46000 -j NFQUEUE --queue-num 0\n"
    )

    nfqueue = NetfilterQueue()
    nfqueue.bind(0, fix_packet)
    try:
        nfqueue.run()
    except KeyboardInterrupt:
        logger_zh.info("\n正在停止抓包...")
        logger_en.info("\nStopping packet hook...")
    finally:
        nfqueue.unbind()


if __name__ == "__main__":
    linux_packet_hook()
