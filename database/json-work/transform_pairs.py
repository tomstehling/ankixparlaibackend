import json


def expand_relations(objects_file, relations_file, output_file):
    """
    Replaces tag names in a relations file with their full JSON objects.
    """
    try:
        # 1. Load both JSON files
        with open(objects_file, "r", encoding="utf-8") as f:
            objects_data = json.load(f)

        with open(relations_file, "r", encoding="utf-8") as f:
            relations_data = json.load(f)

    except FileNotFoundError as e:
        print(f"Error: Could not find a required file. {e}")
        return
    except json.JSONDecodeError as e:
        print(f"Error: Could not parse JSON from a file. {e}")
        return

    # 2. Create a dictionary for fast lookups (name -> full_object)
    # This is the most important step for performance.
    print("Indexing objects by name for fast lookup...")
    objects_map = {item["name"]: item for item in objects_data}

    # 3. Iterate through the relations and build the new expanded list
    expanded_relations = []
    skipped_count = 0
    for pair in relations_data:
        prerequisite_name, concept_name = pair

        # Look up the full objects using our map
        prerequisite_obj = objects_map.get(prerequisite_name)
        concept_obj = objects_map.get(concept_name)

        # Check if both objects were found before creating the new entry
        if prerequisite_obj and concept_obj:
            new_entry = {
                "relationship_type": "analogy",
                "analogy": prerequisite_obj,
                "concept": concept_obj,
            }
            expanded_relations.append(new_entry)
        else:
            # Report any names that couldn't be found
            if not prerequisite_obj:
                print(
                    f"Warning: Could not find object for name '{prerequisite_name}'. Skipping pair {pair}."
                )
            if not concept_obj:
                print(
                    f"Warning: Could not find object for name '{concept_name}'. Skipping pair {pair}."
                )
            skipped_count += 1

    # 4. Write the final list to the output file
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(expanded_relations, f, indent=2, ensure_ascii=False)

    print("\n---")
    print(
        f"✅ Success! Created '{output_file}' with {len(expanded_relations)} expanded relationships."
    )
    if skipped_count > 0:
        print(f"⚠️ Skipped {skipped_count} pairs due to missing names.")


# --- Configuration and Execution ---
if __name__ == "__main__":
    objects_filename = "grammar-tags-lite.json"
    relations_filename = "analogy_relations.json"
    output_filename = "expanded_analogy_relations.json"

    expand_relations(objects_filename, relations_filename, output_filename)
