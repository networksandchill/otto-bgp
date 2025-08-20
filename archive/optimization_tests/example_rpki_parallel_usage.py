#!/usr/bin/env python3
"""
Example usage of RPKI parallel validation in Otto BGP.

Demonstrates how to use the new parallel validation features
for enhanced performance in RPKI validation workflows.
"""

import sys
from pathlib import Path

# Add otto_bgp to path 
sys.path.insert(0, str(Path(__file__).parent))

def example_basic_parallel_validation():
    """Basic example of parallel RPKI validation"""
    
    print("🚀 Basic Parallel RPKI Validation Example")
    print("=" * 45)
    
    try:
        from otto_bgp.validators.rpki import RPKIValidator
        
        # Initialize validator
        validator = RPKIValidator(fail_closed=False)  # For demo purposes
        
        # Example prefix list
        test_prefixes = [
            "192.168.1.0/24",
            "10.0.0.0/16",
            "172.16.0.0/20",
            "203.0.113.0/24",
            "198.51.100.0/24",
            "192.0.2.0/24"
        ]
        
        test_asn = 64512
        
        print(f"📋 Validating {len(test_prefixes)} prefixes for AS{test_asn}")
        print()
        
        # Sequential validation (original method)
        print("🔄 Sequential validation:")
        sequential_results = [validator.validate_prefix_origin(prefix, test_asn) for prefix in test_prefixes]
        print(f"✅ Completed: {len(sequential_results)} results")
        
        # Parallel validation (new method)
        print()
        print("⚡ Parallel validation:")
        parallel_results = validator.validate_prefixes_parallel(test_prefixes, test_asn)
        print(f"✅ Completed: {len(parallel_results)} results")
        
        # Compare results
        print()
        print("📊 Results comparison:")
        print("Prefix           | Sequential | Parallel | Match")
        print("-" * 50)
        
        for i, (seq, par) in enumerate(zip(sequential_results, parallel_results)):
            match = "✅" if seq.state == par.state else "❌"
            print(f"{seq.prefix:<16} | {seq.state.value:<10} | {par.state.value:<8} | {match}")
        
    except ImportError:
        print("⚠️  Demo mode: otto_bgp not available")
        print("📝 This example shows how to use parallel validation:")
        print()
        print("# Initialize validator")
        print("validator = RPKIValidator()")
        print()
        print("# Use parallel validation for multiple prefixes")
        print("results = validator.validate_prefixes_parallel(prefixes, asn)")
        print()
        print("# Or use parallel policy validation")
        print("policy_results = validator.validate_policy_prefixes_parallel(policy)")

def example_policy_validation():
    """Example of parallel policy validation"""
    
    print()
    print("📋 Parallel Policy Validation Example")
    print("=" * 40)
    
    # Example policy data
    example_policy = {
        'as_number': 64512,
        'content': '''
        prefix-list AS64512 {
            192.168.1.0/24;
            10.0.0.0/16;
            172.16.0.0/20;
            203.0.113.0/24;
            198.51.100.0/24;
            192.0.2.0/24;
            203.0.114.0/24;
            198.51.101.0/24;
            192.0.3.0/24;
            10.1.0.0/16;
            172.17.0.0/20;
            203.0.115.0/24;
        }
        '''
    }
    
    print(f"🏢 Policy for AS{example_policy['as_number']}")
    prefix_count = example_policy['content'].count('/24') + example_policy['content'].count('/16') + example_policy['content'].count('/20')
    print(f"📊 Estimated {prefix_count} prefixes in policy")
    
    try:
        from otto_bgp.validators.rpki import RPKIValidator
        
        validator = RPKIValidator(fail_closed=False)
        
        print()
        print("🔄 Running parallel policy validation...")
        results = validator.validate_policy_prefixes_parallel(example_policy)
        
        print(f"✅ Validation completed: {len(results)} results")
        
        # Summarize results
        from collections import Counter
        states = Counter(result.state.value for result in results)
        
        print()
        print("📈 Validation summary:")
        for state, count in states.items():
            print(f"  • {state.upper()}: {count}")
        
    except ImportError:
        print("⚠️  Demo mode: showing example usage")
        print()
        print("# Validate entire policy in parallel")
        print("validator = RPKIValidator()")
        print("results = validator.validate_policy_prefixes_parallel(policy)")
        print()
        print("# With custom worker count")
        print("results = validator.validate_policy_prefixes_parallel(policy, max_workers=4)")

def example_guardrail_integration():
    """Example of RPKI guardrail with parallel validation"""
    
    print()
    print("🛡️ RPKI Guardrail Integration Example")
    print("=" * 40)
    
    try:
        from otto_bgp.validators.rpki import RPKIValidator, RPKIGuardrail
        from otto_bgp.appliers.guardrails import GuardrailConfig
        
        # Initialize components
        validator = RPKIValidator(fail_closed=False)
        config = GuardrailConfig(strictness_level="medium")
        guardrail = RPKIGuardrail(rpki_validator=validator, config=config)
        
        # Example context with multiple policies
        context = {
            'policies': [
                {
                    'as_number': 64512,
                    'content': 'prefix-list AS64512 { 192.168.1.0/24; 10.0.0.0/16; }'
                },
                {
                    'as_number': 64513,
                    'content': 'prefix-list AS64513 { 203.0.113.0/24; 198.51.100.0/24; }'
                }
            ]
        }
        
        print("🔍 Running RPKI guardrail check with parallel validation...")
        result = guardrail.check(context)
        
        print(f"✅ Guardrail result: {'PASSED' if result.passed else 'FAILED'}")
        print(f"🎯 Risk level: {result.risk_level}")
        print(f"💬 Message: {result.message}")
        
    except ImportError:
        print("⚠️  Demo mode: showing guardrail integration")
        print()
        print("# RPKI guardrail automatically uses parallel validation")
        print("guardrail = RPKIGuardrail(rpki_validator=validator)")
        print("result = guardrail.check(context)")
        print()
        print("# Enhanced performance for large policy sets")
        print("# Maintains same security and accuracy guarantees")

def example_performance_tuning():
    """Example of performance tuning options"""
    
    print()
    print("⚡ Performance Tuning Examples")
    print("=" * 32)
    
    print("💡 Performance optimization tips:")
    print()
    
    print("1️⃣ Automatic mode selection:")
    print("   • ≤10 prefixes: Sequential (minimal overhead)")
    print("   • >10 prefixes: Parallel (optimal performance)")
    print()
    
    print("2️⃣ Custom worker count:")
    print("   validator.validate_prefixes_parallel(prefixes, asn, max_workers=4)")
    print()
    
    print("3️⃣ Policy-level parallelization:")
    print("   validator.validate_policy_prefixes_parallel(policy)")
    print()
    
    print("4️⃣ Guardrail optimization:")
    print("   # Guardrails automatically use parallel validation")
    print("   # No code changes needed!")
    print()
    
    print("📊 Expected performance improvements:")
    print("   • 10-50 prefixes: ~2.5x speedup")
    print("   • 50-100 prefixes: ~3.0x speedup") 
    print("   • 100+ prefixes: ~3.3x speedup")

def main():
    """Run all examples"""
    
    print("🎯 RPKI Parallel Validation Usage Examples")
    print("=" * 45)
    print()
    
    # Run examples
    example_basic_parallel_validation()
    example_policy_validation()
    example_guardrail_integration()
    example_performance_tuning()
    
    print()
    print("📚 Additional Resources")
    print("=" * 22)
    print("• Module documentation: otto_bgp/validators/rpki.py")
    print("• Performance tests: test_rpki_parallel_performance.py")
    print("• Accuracy tests: test_rpki_parallel_accuracy.py")
    print("• Integration tests: test_rpki_parallel_integration.py")
    print()
    print("🚀 Ready to use parallel RPKI validation in production!")

if __name__ == "__main__":
    main()