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
import struct
from netfilterqueue import NetfilterQueue
from scapy.all import IP, UDP, Raw, bytes_hex


def get_timestamp():
    return datetime.datetime.now().strftime("%H:%M:%S")


def fix_packet(pkt):
    """Called by nfqueue for every matching packet."""
    from scapy.all import IP, UDP

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
        print(
            f"[EN] Receive packet: client (your partner)'s search request from {src_addr}"
        )
    elif is_outbound and is_search_packet:
        print(f"[EN] Send packet: game broadcast search packet using {src_addr}")
    elif is_inbound and is_hostinfo_packet:
        print(f"[EN] Receive packet: host (your partner)'s info packet from {src_addr}")
    elif is_outbound and is_hostinfo_packet:
        print(
            f"[EN] Send packet: game broadcast host info packet (to your partner) using {src_addr}"
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

        print(f"[EN] Change host IP in info packet to: {partner_ip}")

        # Rebuild scapy packet with modified payload
        scapy_pkt[UDP].remove_payload()
        scapy_pkt = scapy_pkt / Raw(load=bytes(payload))

        # Recalculate checksums
        del scapy_pkt[IP].chksum
        del scapy_pkt[UDP].chksum
        scapy_pkt = IP(bytes(scapy_pkt))

        pkt.set_payload(bytes(scapy_pkt))
        print("[EN] Packet forwarded to game!")
    else:
        if is_outbound:
            print("[EN] Packet forwarded to network adapter.")

    print()
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


def packet_hook():
    print("[EN] Start monitoring UDP port 46000 packets...")
    print(f"[EN] Local IP detected as: {get_local_ip()}")
    print()
    print("Make sure iptables rules are set:")
    print("  sudo iptables -I INPUT  -p udp --dport 46000 -j NFQUEUE --queue-num 0")
    print("  sudo iptables -I OUTPUT -p udp --dport 46000 -j NFQUEUE --queue-num 0")
    print()

    nfqueue = NetfilterQueue()
    nfqueue.bind(0, fix_packet)
    try:
        nfqueue.run()
    except KeyboardInterrupt:
        print("\nStopping packet hook...")
    finally:
        nfqueue.unbind()


if __name__ == "__main__":
    packet_hook()
