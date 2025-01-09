import re
import subprocess

def find_broadcast_priority():
    # The game use the interface that has the smallest hop count to 255.255.255.255
    # We try to parse the route table to get the interface in advance, for user to debug easier
    result = subprocess.run(['route', 'print'], capture_output=True, text=True)
    output = result.stdout

    pattern = re.compile(r'^\s*255\.255\.255\.255\s+(\S+)\s+(\S+)\s+(\S+)\s+(\d+)\s*$', re.MULTILINE)
    matches = pattern.findall(output)
    result = None
    for match in matches:
        netmask, gateway, interface, metric = match
        if not result or int(metric) < int(result[3]):
            result = match
    if result is None:
        return ''
    return result[2]

if __name__ == '__main__':
    print(find_broadcast_priority())