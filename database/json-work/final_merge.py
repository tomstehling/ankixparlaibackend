import json


def create_db_import_file(objects_file, relations_files_map, output_file):
    """
    Merges multiple relationship files into a single file ready for DB import.
    It converts tag names to tag IDs.
    """
    try:
        # 1. Load the main objects file and create a name -> ID lookup map.
        # This is the most efficient way to handle lookups.
        with open(objects_file, "r", encoding="utf-8") as f:
            objects_data = json.load(f)

        print("Indexing objects: creating name-to-ID map...")
        name_to_id_map = {item["name"]: item["id"] for item in objects_data}
        print(f"Indexed {len(name_to_id_map)} unique objects.")

    except FileNotFoundError:
        print(f"FATAL ERROR: The main objects file '{objects_file}' was not found.")
        return
    except (json.JSONDecodeError, KeyError):
        print(
            f"FATAL ERROR: Could not parse '{objects_file}' or it has an invalid format."
        )
        return

    # 2. Iterate through each relationship file and process it.
    all_relationships = []
    total_skipped = 0

    for filename, relationship_type in relations_files_map.items():
        print(
            f"\nProcessing '{filename}' for relationship type: '{relationship_type}'..."
        )
        try:
            with open(filename, "r", encoding="utf-8") as f:
                relations_data = json.load(f)
        except FileNotFoundError:
            print(f"  -> WARNING: File not found. Skipping.")
            continue
        except json.JSONDecodeError:
            print(f"  -> WARNING: Could not parse JSON from file. Skipping.")
            continue

        file_skipped = 0
        for pair in relations_data:
            source_name, target_name = pair

            # 3. Look up the IDs for the source and target names.
            source_id = name_to_id_map.get(source_name)
            target_id = name_to_id_map.get(target_name)

            # 4. If both IDs are found, create the database-ready record.
            if source_id is not None and target_id is not None:
                db_record = {
                    "source_tag_id": source_id,
                    "target_tag_id": target_id,
                    "relationship_type": relationship_type,
                    "weight": 1.0,  # Default weight as per schema
                }
                all_relationships.append(db_record)
            else:
                # Handle cases where a name in a pair doesn't exist in objects.json
                if source_id is None:
                    print(f"  -> Skipping pair: source tag '{source_name}' not found.")
                if target_id is None:
                    print(f"  -> Skipping pair: target tag '{target_name}' not found.")
                file_skipped += 1

        print(
            f"  -> Processed {len(relations_data) - file_skipped} valid pairs. Skipped {file_skipped}."
        )
        total_skipped += file_skipped

    # 5. Write the final merged list to the output file.
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(all_relationships, f, indent=2, ensure_ascii=False)

    print("\n---")
    print("✅ Success! All files processed.")
    print(
        f"Created '{output_file}' with {len(all_relationships)} total relationship records."
    )
    if total_skipped > 0:
        print(f"⚠️ A total of {total_skipped} pairs were skipped due to missing tags.")


# --- Configuration and Execution ---
if __name__ == "__main__":
    # --- YOU NEED TO CONFIGURE THIS SECTION ---

    # 1. The main file with tag objects (id, name, etc.)
    OBJECTS_FILENAME = "grammar_tags.json"

    # 2. A map of your relationship filenames to their type string
    RELATIONSHIP_FILES = {
        "prerequisite_relations.json": "prerequisite",
        "co-requisite_relations.json": "co-requisite",
        "hirarchy_relations.json": "hirarchy",
        "analogy_relations.json": "analogy",
        "dependency_relations.json": "dependency",
    }

    # 3. The name of the final output file
    OUTPUT_FILENAME = "tag_relationships.json"

    # --- Run the script ---
    create_db_import_file(OBJECTS_FILENAME, RELATIONSHIP_FILES, OUTPUT_FILENAME)
