import re
import subprocess
import sys


def find_broadcast_priority():
    """
    Finds the network interface with the smallest hop count (metric) to 255.255.255.255.
    Works natively on both Windows and Linux.
    """
    if sys.platform == "win32":
        try:
            result = subprocess.run(["route", "print"], capture_output=True, text=True)
            pattern = re.compile(
                r"^\s*255\.255\.255\.255\s+(\S+)\s+(\S+)\s+(\S+)\s+(\d+)\s*$",
                re.MULTILINE,
            )
            matches = pattern.findall(result.stdout)

            best_match = None
            for match in matches:
                # match[3] is the metric, match[2] is the interface IP
                if not best_match or int(match[3]) < int(best_match[3]):
                    best_match = match

            return best_match[2] if best_match else ""

        except FileNotFoundError:
            return ""
    elif sys.platform.startswith("linux"):
        try:
            result = subprocess.run(
                ["ip", "route", "get", "255.255.255.255"],
                capture_output=True,
                text=True,
            )

            # Output typically includes "dev <interface_name>" (e.g., "dev eth0")
            match = re.search(r"dev\s+(\S+)", result.stdout)
            return match.group(1) if match else ""

        except FileNotFoundError:
            return ""

    # Fallback
    return ""


if __name__ == "__main__":
    print(find_broadcast_priority())
