"""Test TopicTagger standalone to verify Phase 2 integration."""
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / 'src'))

from ingestion.topic_tagger import TopicTagger


def test_topic_tagger():
    """Test TopicTagger with sample content."""
    print("=" * 80)
    print("PHASE 2 STANDALONE TEST: TopicTagger")
    print("=" * 80)
    
    tagger = TopicTagger()
    
    test_cases = [
        {
            "content": "The System Database is the centralized configuration store for all components in a multi-tier Niagara architecture. It enables enterprise-level deployments spanning multiple supervisors.",
            "section_title": "System Database Overview",
            "expected_topics": ["system_database", "multi_tier_architecture"]
        },
        {
            "content": "To create graphics that display data from multiple supervisors, use tag-based visualization with the System Database. This allows graphics to reference components across the entire enterprise network.",
            "section_title": "Graphics Design",
            "expected_topics": ["graphics", "system_database", "multi_tier_architecture"]
        },
        {
            "content": "Backup and restore procedures ensure data integrity. Use the Archive Manager to create snapshots of station configurations before making changes.",
            "section_title": "Backup Procedures",
            "expected_topics": ["provisioning"]
        },
        {
            "content": "Troubleshooting network connectivity issues between JACE controllers and the supervisor station.",
            "section_title": "Network Troubleshooting",
            "expected_topics": ["troubleshooting", "hardware"]
        },
        {
            "content": "Configure alarm routing by setting up email notifications and mapping alarm sources to recipients.",
            "section_title": "Alarm Configuration",
            "expected_topics": ["configuration"]
        }
    ]
    
    print(f"\n🧪 Running {len(test_cases)} test cases...\n")
    
    passed = 0
    failed = 0
    
    for i, test in enumerate(test_cases, 1):
        print(f"Test {i}: {test['section_title']}")
        print(f"  Content: {test['content'][:80]}...")
        
        topics = tagger.tag_chunk(test['content'], test['section_title'])
        
        print(f"  Expected: {test['expected_topics']}")
        print(f"  Got:      {topics}")
        
        # Check if at least one expected topic is present
        has_match = any(exp in topics for exp in test['expected_topics'])
        
        if has_match:
            print(f"  ✅ PASS")
            passed += 1
        else:
            print(f"  ❌ FAIL - No matching topics")
            failed += 1
        
        print()
    
    print("=" * 80)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 80)
    
    if failed == 0:
        print("\n✅ TopicTagger is working correctly!")
        print("✅ Phase 2 integration verified!")
        return True
    else:
        print(f"\n⚠️  {failed} test(s) failed - review topic tagging logic")
        return False


if __name__ == "__main__":
    success = test_topic_tagger()
    sys.exit(0 if success else 1)
