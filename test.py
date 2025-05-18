def correct_ocr_sequence_non_decreasing(
    ocr_values: list[str],
    default_first_value: int = 1
) -> list[str]:
    """
    Corrects errors in a list of OCR'd numerical strings, assuming
    the underlying sequence is non-decreasing (can stay the same or increase).

    - If a value is parsable and >= the previously corrected value, it's accepted.
    - If a value is parsable but < the previously corrected value, it's an error
      and corrected to the previously corrected value.
    - If a value is not parsable:
        - If it's the first value, it's corrected to `default_first_value`.
        - Otherwise, it's corrected to the previously corrected value.

    Args:
        ocr_values: A list of strings, where each string is expected
                    to represent an integer (or could be empty/invalid).
        default_first_value: The integer value to use if the very first
                             OCR value is unparsable.

    Returns:
        A new list of strings with corrected values, maintaining
        a non-decreasing sequence.
    """
    if not ocr_values:
        return []

    corrected_values_str = []
    # Initialize with a value that would be less than any typical first number,
    # or handle the first element explicitly.
    # Using -1 assumes positive integers; adjust if 0 or negative numbers are possible.
    previous_corrected_num_int = -1 # Sentinel: Not yet properly initialized

    for i, current_val_str in enumerate(ocr_values):
        current_val_int = None
        is_parsable = False

        if current_val_str and current_val_str.strip():
            try:
                current_val_int = int(current_val_str)
                is_parsable = True
            except ValueError:
                # Not a valid integer, is_parsable remains False
                pass

        corrected_num_to_add_int = -1 # Placeholder

        if i == 0: # First element
            if is_parsable:
                corrected_num_to_add_int = current_val_int
            else:
                # First element is not parsable, use default
                corrected_num_to_add_int = default_first_value
            previous_corrected_num_int = corrected_num_to_add_int
        else: # Subsequent elements
            if is_parsable:
                if current_val_int >= previous_corrected_num_int:
                    # Parsable and non-decreasing: accept it
                    corrected_num_to_add_int = current_val_int
                    previous_corrected_num_int = current_val_int
                else:
                    # Parsable but a dip (e.g., 8 then 3): OCR error, assume it was the previous value
                    corrected_num_to_add_int = previous_corrected_num_int
                    # previous_corrected_num_int remains the same (the higher value)
            else:
                # Not parsable: assume it's the same as the last known good value
                corrected_num_to_add_int = previous_corrected_num_int
                # previous_corrected_num_int remains the same

        corrected_values_str.append(str(corrected_num_to_add_int))

    return corrected_values_str

# --- Example Usage ---
if __name__ == '__main__':
    ocr_output_data_problematic = [
        "1", "2", "8", "3", "4", "5", "6", "7", "8", "3", "3", "8", "9", "10", "11", "12", "13", "14", "15", "16",
        "17", "13", "19", "20", "21", "22", "28", "24", "25", "26", "27", "28", "29", "30", "30", "30", "30",
        "31", "31", "31", "32", "32", "32", "33", "33", "33", "34", "35", "36", "37", "33", "39", "40", "41",
        "42", "43", "45", "46", "48", "49", "50", "50", "50", "50", "50", "50", "50", "50", "50", "50", "50",
        "50", "50", "51", "51", "52", "53", "54", "54", "54", "54", "54", "55", "55", "56", "56", "57", "57",
        "58", "59", "60", "60", "61", "62", "63", "64", "65", "67", "68", "69", "70", "71", "72", "73", "75",
        "76", "77", "79", "80", "81", "32", "83", "85", "86", "37", "83", "90", "90", "91", "92", "93", "95",
        "96", "97", "93", "99"
    ]

    print("--- Testing with the initial problematic sequence ---")
    corrected_problematic_data = correct_ocr_sequence_non_decreasing(ocr_output_data_problematic)

    print("Idx | Orig | Corr | Comment")
    print("----|------|------|-------------------------------------------")
    for i in range(min(20, len(ocr_output_data_problematic))): # Print first 20
        orig_val = ocr_output_data_problematic[i]
        corr_val = corrected_problematic_data[i]
        comment = "OK" if orig_val == corr_val and int(corr_val) >= (int(corrected_problematic_data[i-1]) if i > 0 else -1) else f"Fix: {orig_val} -> {corr_val}"
        print(f"{i:<3} | {orig_val:>4} | {corr_val:>4} | {comment}")

    print("\n--- Testing with sequence including repeats and specific errors ---")
    # Example: 1 1 1 2 2 3 (OCR:8) (OCR:3) (OCR:8) (OCR:3) (OCR:8) (OCR:3) (OCR:3) (OCR:8) (OCR:4) (OCR:4) 5
    test_sequence_repeats = [
        "1", "1", "1", "2", "2", "3", "8", "3", "8", "3", "8", "3", "3", "8", "4", "4", "5", "", "foo", "5"
    ]
    # Expected: 1 1 1 2 2 3 8 8 8 8 8 8 8 8 8 8 8 8 8 8 (last "5" keeps the previous "8" because it was not parsable, then foo also, then 5 is < 8)
    # Ah, if "5" is the last element, and previous was "8", it will become "8".
    # Let's re-evaluate test_sequence_repeats with the logic:
    # 1,1,1,2,2,3 -> prev=3
    # 8 (curr=8 >= prev=3) -> val=8, prev=8
    # 3 (curr=3 < prev=8)  -> val=8, prev=8
    # 8 (curr=8 >= prev=8) -> val=8, prev=8
    # 3 (curr=3 < prev=8)  -> val=8, prev=8
    # 8 (curr=8 >= prev=8) -> val=8, prev=8
    # 3 (curr=3 < prev=8)  -> val=8, prev=8
    # 3 (curr=3 < prev=8)  -> val=8, prev=8
    # 8 (curr=8 >= prev=8) -> val=8, prev=8
    # 4 (curr=4 < prev=8)  -> val=8, prev=8
    # 4 (curr=4 < prev=8)  -> val=8, prev=8
    # 5 (curr=5 < prev=8)  -> val=8, prev=8
    # "" (not parsable)    -> val=8, prev=8
    # "foo" (not parsable) -> val=8, prev=8
    # "5" (curr=5 < prev=8)  -> val=8, prev=8
    # Expected corrected: 1 1 1 2 2 3 8 8 8 8 8 8 8 8 8 8 8 8 8 8

    print(f"Original: {test_sequence_repeats}")
    corrected_repeats = correct_ocr_sequence_non_decreasing(test_sequence_repeats)
    print(f"Corrected: {corrected_repeats}")

    print("\n--- Testing specific problematic section from user example ---")
    # Indices based on original full list for context: 81, "32", 83, 85, 86, "37", 83, 90
    # Input slice: "81", "32", "83", "85", "86", "37", "83", "90"
    # (Assuming previous corrected value was <= 81)
    # Let's test if the value before "81" was, say, "80"
    # So previous_corrected_num_int for the first "81" would be "80".
    
    # To test a slice, we need to provide a "previous_corrected_num_int" or run it from start
    # Let's use indices from the main example: 90 to 97
    # ocr_output_data_problematic[90:98] is ['81', '32', '83', '85', '86', '37', '83', '90']
    # corrected_problematic_data[89] is '80' (this will be prev_corr_int for '81')

    print("\nIdx | Orig | Corr | Comment (Context: previous corrected val was 80)")
    print("----|------|------|-------------------------------------------")
    # Manually trace this segment to match the full run:
    # prev_corr = 80 (from corrected_problematic_data[89])
    # Orig: 81. 81 >= 80. Corrected: 81. prev_corr = 81.
    # Orig: 32. 32 < 81.  Corrected: 81. prev_corr = 81.
    # Orig: 83. 83 >= 81. Corrected: 83. prev_corr = 83.
    # Orig: 85. 85 >= 83. Corrected: 85. prev_corr = 85.
    # Orig: 86. 86 >= 85. Corrected: 86. prev_corr = 86.
    # Orig: 37. 37 < 86.  Corrected: 86. prev_corr = 86.
    # Orig: 83. 83 < 86.  Corrected: 86. prev_corr = 86.
    # Orig: 90. 90 >= 86. Corrected: 90. prev_corr = 90.

    # Expected corrected for this slice: ['81', '81', '83', '85', '86', '86', '86', '90']
    # Check against full run:
    # corrected_problematic_data[90:98] should be this.
    
    start_idx_slice = 90
    end_idx_slice = 98
    print(f"Original slice (idx {start_idx_slice}-{end_idx_slice-1}): {ocr_output_data_problematic[start_idx_slice:end_idx_slice]}")
    print(f"Corrected slice (idx {start_idx_slice}-{end_idx_slice-1}): {corrected_problematic_data[start_idx_slice:end_idx_slice]}")
    
    for i in range(start_idx_slice, end_idx_slice):
        orig_val = ocr_output_data_problematic[i]
        corr_val = corrected_problematic_data[i]
        # prev_actual_corr_val for comment:
        prev_actual_corr_val = int(corrected_problematic_data[i-1]) if i > 0 else -1000 # some small num
        
        comment = ""
        if not (orig_val.isdigit() and int(orig_val) == int(corr_val) and int(corr_val) >= prev_actual_corr_val):
             comment = f"Fix: {orig_val} -> {corr_val}"
        else:
            comment = "OK"

        print(f"{i:<3} | {orig_val:>4} | {corr_val:>4} | {comment} (prev_corr_was: {prev_actual_corr_val})")

    print("\n--- Test with empty strings / failed extractions ---")
    ocr_output_with_blanks = ["1", "", "8", "3", "4", "", "6", "5", "foo", "7"]
    # Expected:
    # 1 (prev=1)
    # "" -> 1 (prev=1)
    # 8 (8>=1) -> 8 (prev=8)
    # 3 (3<8) -> 8 (prev=8)
    # 4 (4<8) -> 8 (prev=8)
    # "" -> 8 (prev=8)
    # 6 (6<8) -> 8 (prev=8)
    # 5 (5<8) -> 8 (prev=8)
    # foo -> 8 (prev=8)
    # 7 (7<8) -> 8 (prev=8)
    # Corrected: ['1', '1', '8', '8', '8', '8', '8', '8', '8', '8']
    print(f"Original with blanks: {ocr_output_with_blanks}")
    corrected_blanks = correct_ocr_sequence_non_decreasing(ocr_output_with_blanks)
    print(f"Corrected with blanks: {corrected_blanks}")

    print("\n--- Test starting with empty/invalid ---")
    ocr_start_invalid = ["", "foo", "2", "1", "3"]
    # Expected:
    # "" (first, invalid) -> 1 (default_first_value) (prev=1)
    # "foo" (invalid) -> 1 (prev=1)
    # "2" (2>=1) -> 2 (prev=2)
    # "1" (1<2) -> 2 (prev=2)
    # "3" (3>=2) -> 3 (prev=3)
    # Corrected: ['1', '1', '2', '2', '3']
    print(f"Original start invalid: {ocr_start_invalid}")
    corrected_start_invalid = correct_ocr_sequence_non_decreasing(ocr_start_invalid)
    print(f"Corrected start invalid: {corrected_start_invalid}")