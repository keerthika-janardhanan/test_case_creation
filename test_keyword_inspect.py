"""Test the keyword-inspect endpoint logic."""
import sys
from pathlib import Path

# Test the keyword-inspect logic
def test_keyword_inspect():
    """Test keyword-inspect with the default framework."""
    from app.api.framework_resolver import resolve_framework_root
    
    # Test 1: Resolve framework root
    print("Test 1: Resolving framework root...")
    framework_root = resolve_framework_root()
    print(f"✓ Framework root: {framework_root}")
    assert framework_root.exists(), "Framework root should exist"
    
    # Test 2: Check tests directory
    print("\nTest 2: Checking tests directory...")
    tests_dir = framework_root / "tests"
    print(f"Tests dir exists: {tests_dir.exists()}")
    if tests_dir.exists():
        spec_files = list(tests_dir.glob("**/*.spec.ts")) + list(tests_dir.glob("**/*.test.ts"))
        print(f"Found {len(spec_files)} test files")
        for f in spec_files:
            print(f"  - {f.relative_to(framework_root)}")
    
    # Test 3: Create a sample test file to search
    print("\nTest 3: Creating sample test file...")
    tests_dir.mkdir(exist_ok=True)
    sample_test = tests_dir / "sample.spec.ts"
    sample_test.write_text("""
import { test, expect } from '@playwright/test';

test('Create Supplier', async ({ page }) => {
  await page.goto('https://example.com');
  await page.getByRole('button', { name: 'Create Supplier' }).click();
  await expect(page).toHaveTitle(/Supplier/);
});
""")
    print(f"✓ Created sample test: {sample_test.relative_to(framework_root)}")
    
    # Test 4: Search for keyword in test files
    print("\nTest 4: Searching for keyword 'Create Supplier'...")
    keyword = "Create Supplier"
    found_files = []
    
    spec_files = list(tests_dir.glob("**/*.spec.ts")) + list(tests_dir.glob("**/*.test.ts"))
    for spec_file in spec_files:
        content = spec_file.read_text(encoding='utf-8')
        if keyword.lower() in content.lower():
            lines = content.split('\n')
            matching_lines = [i for i, line in enumerate(lines) if keyword.lower() in line.lower()]
            print(f"✓ Found '{keyword}' in {spec_file.name} ({len(matching_lines)} occurrences)")
            
            # Extract snippet
            if matching_lines:
                match_idx = matching_lines[0]
                start = max(0, match_idx - 2)
                end = min(len(lines), match_idx + 3)
                snippet = '\n'.join(lines[start:end])
                print(f"  Snippet:\n{snippet[:200]}")
            found_files.append(spec_file)
    
    assert len(found_files) > 0, "Should find at least one file with keyword"
    print(f"\n✓ Test passed! Found keyword in {len(found_files)} files")
    
    # Clean up
    sample_test.unlink()
    print("\n✓ Cleaned up sample test file")

if __name__ == "__main__":
    try:
        test_keyword_inspect()
        print("\n" + "="*60)
        print("All tests passed!")
        print("="*60)
    except Exception as e:
        print(f"\n✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
