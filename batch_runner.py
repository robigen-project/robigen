
import os
import sys

def get_input(prompt, default=None):
    """Get input with optional default value."""
    if default:
        user_input = input(f"{prompt} (default: {default}): ").strip()
        return user_input if user_input else default
    return input(f"{prompt}: ").strip()

def collect_task_data(task_name, needs_attribute=False):
    """Collects configuration for a specific task interactively."""
    print(f"\n--- Configuring Task: {task_name.upper()} ---")
    tasks = []
    
    # We want 2 images per task as per requirement
    for i in range(1, 3):
        print(f"\n[Image {i}/2]")
        image_path = get_input(f"Enter path for Image {i}")
        if not image_path:
            print("Skipping image.")
            continue
            
        # We want 2 objects per image as per requirement
        for j in range(1, 3):
            obj = get_input(f"  Enter Object {j} for {image_path}")
            if not obj:
                print("  Skipping object.")
                continue
                
            task_entry = {"image": image_path, "object": obj}
            
            if needs_attribute:
                attr = get_input(f"  Enter Attribute for '{obj}'")
                task_entry["attribute"] = attr
                
            tasks.append(task_entry)
            
    return tasks

def generate_commands():
    print("="*80)
    print("INTERACTIVE BATCH TEST RUNNER")
    print("="*80)
    print("This wizard will help you generate commands for 4 parallel workers.")
    print("defaults: gemini, 25 iterations (press Enter to accept defaults usually)")
    print("-" * 80)
    
    # Global Settings
    model = get_input("Model to use", default="gemini")
    iterations = get_input("Iterations per scenario", default="25")
    
    # Collect Data for each Worker
    pick_up_data = collect_task_data("Pick Up")
    detection_data = collect_task_data("Detection")
    ambiguity_data = collect_task_data("Ambiguity")
    attribute_data = collect_task_data("Attribute", needs_attribute=True)
    
    # Generate Commands
    commands = {
        "Worker 1 - Pick Up": [],
        "Worker 2 - Detection": [],
        "Worker 3 - Ambiguity": [],
        "Worker 4 - Attribute": []
    }
    
    # Helper to build command string
    def build_cmd(task, data_list):
        cmds = []
        for item in data_list:
            base = f'python test_main.py --task {task} --model {model} --images "{item["image"]}" --objects "{item["object"]}" --iterations {iterations}'
            if "attribute" in item:
                base += f' --attribute "{item["attribute"]}"'
            cmds.append(base)
        return cmds

    commands["Worker 1 - Pick Up"] = build_cmd("pick_up", pick_up_data)
    commands["Worker 2 - Detection"] = build_cmd("detection", detection_data)
    commands["Worker 3 - Ambiguity"] = build_cmd("ambiguity", ambiguity_data)
    commands["Worker 4 - Attribute"] = build_cmd("attribute", attribute_data)
    
    # Output
    print("\n\n" + "="*80)
    print("GENERATED BATCH COMMANDS")
    print("="*80)
    
    for worker, cmds in commands.items():
        print(f"\n### {worker}")
        if not cmds:
            print("# No tasks configured.")
        else:
            print(" && \\\n".join(cmds))
        print("-" * 40)
        
if __name__ == "__main__":
    try:
        generate_commands()
    except KeyboardInterrupt:
        print("\nOperation cancelled.")
        sys.exit(0)
