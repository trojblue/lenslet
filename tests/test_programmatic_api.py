"""Simple test script for the programmatic API."""
import os
import re
import signal
import subprocess
import os
import tempfile
import time
import json
import urllib.request
from pathlib import Path
from PIL import Image


def _terminate_process_on_port(port: int) -> None:
    try:
        output = subprocess.check_output(["ss", "-ltnp"], text=True)
    except Exception:
        return

    pid: int | None = None
    for line in output.splitlines():
        if f":{port}" not in line:
            continue
        match = re.search(r"pid=(\d+)", line)
        if match:
            pid = int(match.group(1))
            break

    if pid is None:
        return

    for sig in (signal.SIGTERM, signal.SIGKILL):
        try:
            os.kill(pid, sig)
        except OSError:
            return
        time.sleep(0.2)

def _run_local_images() -> bool:
    print("\n" + "="*60)
    print("TEST 1: Local Images")
    print("="*60)
    
    # Create some test images in a temporary directory
    temp_dir = tempfile.mkdtemp()
    print(f"✓ Created temp directory: {temp_dir}")
    
    # Create 3 test images
    test_images = []
    for i in range(3):
        img_path = Path(temp_dir) / f"test_image_{i}.jpg"
        img = Image.new('RGB', (800, 600), color=(i * 80, 100, 200))
        img.save(img_path, 'JPEG')
        test_images.append(str(img_path))
    print(f"✓ Created {len(test_images)} test images")
    
    # Test the API
    import lenslet
    
    datasets = {
        "test_set_1": test_images[:2],
        "test_set_2": [test_images[2]],
    }
    
    print(f"✓ Prepared datasets: {list(datasets.keys())}")
    print(f"\nLaunching lenslet on port 7072 (quiet mode)...")
    
    lenslet.launch_datasets(datasets, blocking=False, port=7072, verbose=False)
    
    # Wait for server to start
    time.sleep(3)
    
    # Test endpoints
    try:
        # Health check
        with urllib.request.urlopen("http://127.0.0.1:7072/health") as response:
            data = json.loads(response.read())
            assert data["ok"] == True
            assert data["mode"] == "dataset"
            assert set(data["datasets"]) == set(datasets.keys())
            print("✓ Health check passed")
        
        # Root folder
        with urllib.request.urlopen("http://127.0.0.1:7072/folders?path=/") as response:
            data = json.loads(response.read())
            found_dirs = [d["name"] for d in data["dirs"]]
            assert set(found_dirs) == set(datasets.keys())
            print(f"✓ Root index: found datasets {found_dirs}")
        
        # Dataset folder
        with urllib.request.urlopen("http://127.0.0.1:7072/folders?path=/test_set_1") as response:
            data = json.loads(response.read())
            assert len(data["items"]) == 2
            print(f"✓ Dataset 'test_set_1': {len(data['items'])} images")
            for item in data["items"]:
                print(f"    - {item['name']}: {item['w']}x{item['h']}")
        
        # Thumbnail
        with urllib.request.urlopen("http://127.0.0.1:7072/thumb?path=/test_set_1/test_image_0.jpg") as response:
            thumb_data = response.read()
            assert len(thumb_data) > 0
            assert response.headers.get("Content-Type") == "image/webp"
            print(f"✓ Thumbnail generation: {len(thumb_data)} bytes")
        
        print("\n✅ All local image tests passed!\n")
        return True
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        # Cleanup
        print("Cleaning up...")
        for img in test_images:
            try:
                os.remove(img)
            except:
                pass
        try:
            os.rmdir(temp_dir)
        except:
            pass
        
        _terminate_process_on_port(7072)
        time.sleep(1)


def test_local_images() -> None:
    """Test with local images only."""
    assert _run_local_images()


def _run_api_signature_check() -> bool:
    print("\n" + "="*60)
    print("TEST 2: API Signature")
    print("="*60)
    
    import lenslet
    
    # Just verify the function exists with correct signature
    import inspect
    sig = inspect.signature(lenslet.launch)
    params = list(sig.parameters.keys())
    
    expected = [
        "datasets",
        "blocking",
        "port",
        "host",
        "thumb_size",
        "thumb_quality",
        "show_source",
        "verbose",
    ]
    assert params == expected, f"Expected {expected}, got {params}"
    print(f"✓ Function signature correct: {params}")
    assert hasattr(lenslet, "launch_datasets")
    assert hasattr(lenslet, "launch_table")
    
    # Verify defaults
    assert sig.parameters["blocking"].default == False
    assert sig.parameters["port"].default == 7070
    assert sig.parameters["host"].default == "127.0.0.1"
    assert sig.parameters["show_source"].default == True
    assert sig.parameters["verbose"].default == False

    table_sig = inspect.signature(lenslet.launch_table)
    table_params = list(table_sig.parameters.keys())
    assert table_params == [
        "table",
        "blocking",
        "port",
        "host",
        "thumb_size",
        "thumb_quality",
        "show_source",
        "verbose",
        "source_column",
        "base_dir",
    ]
    assert table_sig.parameters["source_column"].default is None
    assert table_sig.parameters["base_dir"].default is None
    print("✓ Default parameters correct")
    
    print("\n✅ API signature test passed!\n")
    return True


def test_blocking_mode() -> None:
    """Test blocking parameter (just verify it can be called)."""
    assert _run_api_signature_check()


if __name__ == "__main__":
    print("\n" + "="*60)
    print("Lenslet Programmatic API Test Suite")
    print("="*60)
    
    results = []
    
    # Run tests
    results.append(("API Signature", _run_api_signature_check()))
    results.append(("Local Images", _run_local_images()))
    
    # Summary
    print("\n" + "="*60)
    print("Test Summary")
    print("="*60)
    
    for name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status}: {name}")
    
    all_passed = all(passed for _, passed in results)
    
    if all_passed:
        print("\n✅ All tests passed!")
        exit(0)
    else:
        print("\n❌ Some tests failed")
        exit(1)
