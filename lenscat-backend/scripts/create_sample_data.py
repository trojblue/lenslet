#!/usr/bin/env python3
"""Create sample data for development."""
import json
import os
from datetime import datetime
from pathlib import Path
from PIL import Image, ImageDraw


def create_sample_image(path: Path, width: int = 400, height: int = 300, color: str = "blue"):
    """Create a sample image."""
    img = Image.new("RGB", (width, height), color)
    draw = ImageDraw.Draw(img)
    
    # Add some text
    text = path.stem
    draw.text((10, 10), text, fill="white")
    
    # Save as JPEG
    img.save(path, "JPEG", quality=85)


def create_sample_sidecar(image_path: Path, tags: list, notes: str = ""):
    """Create a sample sidecar file."""
    sidecar_path = Path(f"{image_path}.json")
    
    sidecar_data = {
        "v": 1,
        "tags": tags,
        "notes": notes,
        "exif": {
            "width": 400,
            "height": 300,
            "created_at": "2024-01-01T12:00:00Z"
        },
        "updated_at": datetime.utcnow().isoformat() + "Z",
        "updated_by": "sample-data-generator"
    }
    
    with open(sidecar_path, "w") as f:
        json.dump(sidecar_data, f, indent=2)


def main():
    """Create sample data structure."""
    data_dir = Path("./data")
    data_dir.mkdir(exist_ok=True)
    
    # Create folder structure
    folders = {
        "landscapes": [
            ("mountain.jpg", ["landscape", "mountain", "nature"], "Beautiful mountain view"),
            ("lake.jpg", ["landscape", "water", "serene"], "Peaceful lake scene"),
            ("sunset.jpg", ["landscape", "sunset", "golden"], "Golden hour magic"),
        ],
        "portraits": [
            ("person1.jpg", ["portrait", "professional"], "Professional headshot"),
            ("person2.jpg", ["portrait", "casual"], "Casual portrait"),
        ],
        "architecture": [
            ("building1.jpg", ["architecture", "modern"], "Modern building design"),
            ("bridge.jpg", ["architecture", "bridge", "urban"], "City bridge"),
        ]
    }
    
    # Create sample images and metadata
    for folder_name, images in folders.items():
        folder_path = data_dir / folder_name
        folder_path.mkdir(exist_ok=True)
        
        for image_name, tags, notes in images:
            image_path = folder_path / image_name
            
            if not image_path.exists():
                # Create sample image with different colors
                color = "blue" if "landscape" in tags else "green" if "portrait" in tags else "red"
                create_sample_image(image_path, color=color)
                
                # Create sidecar
                create_sample_sidecar(image_path, tags, notes)
                
                print(f"Created: {image_path}")
    
    # Create a nested structure
    nested_dir = data_dir / "events" / "2024" / "conference"
    nested_dir.mkdir(parents=True, exist_ok=True)
    
    conference_images = [
        ("keynote.jpg", ["conference", "keynote", "2024"], "Opening keynote"),
        ("panel.jpg", ["conference", "panel", "discussion"], "Expert panel"),
    ]
    
    for image_name, tags, notes in conference_images:
        image_path = nested_dir / image_name
        if not image_path.exists():
            create_sample_image(image_path, color="purple")
            create_sample_sidecar(image_path, tags, notes)
            print(f"Created: {image_path}")
    
    print(f"\n✅ Sample data created in {data_dir.resolve()}")
    print("🖼️  Total structure:")
    print("   ./data/landscapes/ (3 images)")
    print("   ./data/portraits/ (2 images)")  
    print("   ./data/architecture/ (2 images)")
    print("   ./data/events/2024/conference/ (2 images)")
    print("\n🚀 Start the backend with: python scripts/dev.py")


if __name__ == "__main__":
    main()
