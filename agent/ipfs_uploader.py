"""
IPFS Upload Utility for ERC-8004 Agent Registration

Uploads agent registration files to IPFS and returns the CID.
"""
import json
import subprocess
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def upload_to_ipfs(content: str, filename: str = "registration.json") -> Optional[str]:
    """
    Upload content to local IPFS daemon.

    Args:
        content: JSON string to upload
        filename: Name for the uploaded file

    Returns:
        IPFS CID hash, or None if failed
    """
    try:
        # Write content to temp file
        temp_path = Path(f"/tmp/{filename}")
        temp_path.write_text(content)

        # Upload via IPFS CLI
        result = subprocess.run(
            ["ipfs", "add", "-q", str(temp_path)],
            capture_output=True,
            text=True,
            timeout=30
        )

        if result.returncode != 0:
            logger.error(f"IPFS upload failed: {result.stderr}")
            return None

        cid = result.stdout.strip()
        logger.info(f"Uploaded to IPFS: {cid}")

        # Clean up temp file
        temp_path.unlink()

        return cid

    except subprocess.TimeoutExpired:
        logger.error("IPFS upload timed out")
        return None
    except FileNotFoundError:
        logger.error("IPFS CLI not found - is the daemon running?")
        return None
    except Exception as e:
        logger.error(f"IPFS upload error: {e}")
        return None


def upload_registration(registration_dict: dict) -> Optional[str]:
    """
    Upload agent registration to IPFS.

    Args:
        registration_dict: Agent registration data

    Returns:
        IPFS URI (ipfs://CID) or None if failed
    """
    content = json.dumps(registration_dict, indent=2)
    cid = upload_to_ipfs(content, "erc8004_registration.json")

    if cid:
        return f"ipfs://{cid}"
    return None


def pin_cid(cid: str) -> bool:
    """Pin a CID to ensure persistence"""
    try:
        result = subprocess.run(
            ["ipfs", "pin", "add", cid],
            capture_output=True,
            text=True,
            timeout=60
        )
        return result.returncode == 0
    except Exception as e:
        logger.error(f"Pin failed: {e}")
        return False


if __name__ == "__main__":
    # Test upload
    test_data = {
        "name": "test-agent",
        "description": "Test upload",
        "version": "0.1.0",
        "capabilities": ["test"]
    }

    uri = upload_registration(test_data)
    if uri:
        print(f"Registration uploaded: {uri}")
    else:
        print("Upload failed")
