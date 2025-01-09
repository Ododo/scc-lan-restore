import pydivert
import socket
import datetime
from log import logger_zh, logger_en


# This script can be ran after game start.

def packet_hook():
    # Normal connect process:
    # 0. host create session
    # 1. client send search packet: send udp broadcast packet to 255.255.255.255:46000, payload len == 54
    # 2. host respond with session info packet: send udp broadcast packet to 255.255.255.255:46000, payload len > 500, which contains host's ip and mac.
    # 3. client:9103 try to directly connect to host:9103 via udp, using ip in host's info packet.
    # Host info in step 2 can be wrong, causing connection failure, so we need to manually modify it.
    # This can be done either after host sends info packet(on host machine outbound), or before client receives it(on client machine inbound). This function chose the latter option.

    # Note that if modifying inbound packets, wireshark still captures the original packet. (Only modifying outbound packets will cause wireshark to capture the modified one)
    logger_zh.info('开始对搜索房间、加入房间等行为进行抓包，请确认后续日志中的ip地址是否正确，如需修改游戏使用的网卡，请参考README\n')
    logger_en.info(
        'Start monitoring packets for searching for and connecting to sessions, please check if ip address is correct in later logs, and refer to README to change the preferred network interface\n')
    with pydivert.WinDivert("(inbound or outbound) and udp.DstPort == 46000") as w:
        for packet in w:
            print(f'[{datetime.datetime.now().strftime("%H:%M:%S")}]')
            
            src_addr: str = packet.ipv4.src_addr  # format: string "xxx.xxx.xxx.xxx"

            isinbound = packet.is_inbound
            isoutbound = packet.is_outbound
            
            is_search_packet = len(packet.payload) == 54
            is_hostinfo_packet = len(packet.payload) > 500
            
            # log ip address to verify if sent via the correct network adapter
            if isinbound and is_search_packet:
                logger_zh.info(f'收到数据包：\n来自客户端（队友） {src_addr} 的房间搜索请求\n')
                logger_en.info(f'Receive packet: client (your parter)\'s search request from {src_addr}\n')
            elif isoutbound and is_search_packet:
                logger_zh.info(f'发送数据包：\n游戏从 {src_addr} 广播发出房间搜索数据包\n')
                logger_en.info(f'Send packet: game broadcast search packet using {src_addr}\n')
            elif isinbound and is_hostinfo_packet:
                logger_zh.info(f'收到数据包：\n来自房主（队友） {src_addr} 的房间信息数据包\n')
                logger_en.info(f'Receive packet: host (your partner)\'s info packet from {src_addr}\n')
            elif isoutbound and is_hostinfo_packet:
                logger_zh.info(f'发送数据包：\n游戏从 {src_addr} 广播发出房间信息数据包（给队友）\n')
                logger_en.info(f'Send packet: game broadcast host info packet (to your partner) using {src_addr}\n')
            
            # print(f'Session ID: {packet.payload[44:46].hex()}')
            
            if isinbound and len(packet.payload) > 500:
                # This is the host info packet sent to your partner after they send search packet, 
                # we correct it before send to your partner.
                
                payload = bytearray(packet.payload)
                
                # Fix ip field
                # The ip field is of variable length, determined by payload[0x5b] - 1. Followed by available ip fields, each ip field is of 8 Bytes, starts with 0x07, ends with 0x05 0x23 0x8F.
                # A bad packet have 0 ip field.
                # Sometimes a good packet is sent but have more than one ip field, causing client to connect to unreachable ip.
                # Both cases need to be fixed.
                partner_ip = src_addr
                partner_ip_field = bytearray.fromhex('07 {} 05 23 8F'.format(socket.inet_aton(partner_ip).hex()))
                
                num_available_ips = packet.payload[0x5b] - 1
                if num_available_ips == 0:
                    # Insert ip field if it's empty
                    payload = payload[:0x5c] + partner_ip_field + payload[0x5c:]
                elif num_available_ips >= 2:
                    # Remove extra ip fields that mess with further connection
                    payload = payload[:0x5c] + partner_ip_field + payload[0x5c + len(partner_ip_field) * num_available_ips:]
                else:
                    # Update ip field
                    payload[0x5c:0x5c + len(partner_ip_field)] = partner_ip_field
                
                num_available_ips = 1
                payload[0x5b] = num_available_ips + 1  # update available ip count

                logger_zh.info(f'将房间信息中的房主IP改为: {partner_ip}\n')
                logger_en.info(f'Change host IP in info packet to: {partner_ip}\n')
                
                # Override mac field (maybe not necessary, tests show that wrong mac doesn't affect session joining. But keep this code just in case)
                # logger_zh.info(f'房间信息中声明房主 MAC 为: {payload[0x79:0x7f].hex("-")}')
                # logger_en.info(f'Host info packet declares host\'s MAC to be: {payload[0x79:0x7f].hex("-")}')
                # if partner_mac:
                #     partner_mac_field = bytes.fromhex(partner_mac.replace('-', ''))
                #     payload[0x79:0x7f] = partner_mac_field
                #
                #     logger_zh.info(f'将其改为: {partner_mac_field.hex("-")}')
                #     logger_en.info(f'change it into: {partner_mac_field.hex("-")}')
                
                packet.payload = bytes(payload)
            
            # forward the packet
            w.send(packet)
            if isinbound:
                logger_zh.info('数据包已转发给游戏！')
                logger_en.info('Packet forwarded to game!')
            elif isoutbound:
                logger_zh.info('数据包已转发给网卡。')
                logger_en.info('Packet forwarded to network adapter.')
            print('\n')


if __name__ == "__main__":
    packet_hook()
