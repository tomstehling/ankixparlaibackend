import json


def validate_relations(objects_file, relations_file):
    """
    Checks if all names used in the relations file exist in the objects file.
    """
    try:
        with open(objects_file, "r") as f:
            objects_data = json.load(f)

        with open(relations_file, "r") as f:
            relations_data = json.load(f)
    except FileNotFoundError as e:
        print(f"Error: Could not find a file. {e}")
        return
    except json.JSONDecodeError as e:
        print(f"Error: Could not parse JSON from a file. {e}")
        return

    # 1. Create a set of all valid names for fast lookups (O(1) average)
    valid_names = {item["name"] for item in objects_data}

    # 2. Find all unique names used in the relations list
    all_relation_names = set()
    for pair in relations_data:
        all_relation_names.update(pair)

    # 3. Find the names that are in the relations list but NOT in the valid names list
    #    This is easily done by finding the difference between the two sets.
    invalid_names = all_relation_names - valid_names

    # 4. Report the results
    if not invalid_names:
        print("✅ Success! All names in the relations file are valid.")
    else:
        print(f"❌ Found {len(invalid_names)} invalid (made-up) names:")
        for name in sorted(list(invalid_names)):
            print(f"  - {name}")


# --- Run the validation ---

# prerequisits
print("Checking prerequisite relations...")
objects_file = "grammar-tags-lite.json"
relations_file = "prerequisite_relations.json"
validate_relations(objects_file, relations_file)

# hirarchy
print("\nChecking hierarchy relations...")
objects_file = "grammar-tags-lite.json"
relations_file = "hirarchy_relations.json"
validate_relations(objects_file, relations_file)

# dependency
print("\nChecking dependency relations...")
objects_file = "grammar-tags-lite.json"
relations_file = "dependency_relations.json"
validate_relations(objects_file, relations_file)

# co-requisite
print("\nChecking  co-requisite relations...")
objects_file = "grammar-tags-lite.json"
relations_file = "co-requisite_relations.json"
validate_relations(objects_file, relations_file)

# analogy
print("\nChecking analogy relations...")
objects_file = "grammar-tags-lite.json"
relations_file = "analogy_relations.json"
validate_relations(objects_file, relations_file)
