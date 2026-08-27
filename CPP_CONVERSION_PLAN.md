# C++ Conversion Plan for SIH Analytics

## Executive Summary
Convert the Python analytics pipeline to C++ for improved performance while maintaining API compatibility. Target: 10-50x speedup for signal processing, reduced memory footprint, and deployment as a standalone service.

## Current State Analysis
- Python pipeline processes 50 CSEs in ~90 seconds (~1.8s/CSE)
- 25 signals across 5 categories (execution_gap, negative_space, behavioral_anomaly, peer_deviation, reasoning_quality)
- Data structures: pd.DataFrame per entity, investigation notes as strings, keyword-based classification
- 337 existing tests + 20 reasoning quality tests
- SQLite-backed API with FastAPI

## Conversion Strategy: Hybrid Approach

### Phase 1: Core Signal Kernels (C++)
- Convert reasoning quality signal logic (keyword matching, depth scoring, coherence calculation) to C++ 
- Keep DataFrame I/O in Python for compatibility
- Target signal processing: <0.1s per CSE (18x speedup)

### Phase 2: Data Structures (C++ + Python bindings)
- Replace pd.DataFrame with lightweight C++ structs for investigation/alert/escalation records
- Use Arrow columnar format for interop with Python (pybind11 + pyarrow)
- Maintain JSON <-> C++ struct conversion via pybind11

### Phase 3: API Layer (Keep Python / Add C++ Service)
- FastAPI endpoints remain in Python
- Optional C++ microservice for signal computation
- Graceful fallback to Python if C++ unavailable

### Phase 4: Testing & Verification
- 100% test coverage maintained
- Golden output comparison (Python == C++ results)
- Performance benchmarks

## Technical Design

### C++ Components
- **`signal_kernels.cpp`**: Core keyword matching, depth/coherence scoring
- **`reasoning_quality.cpp`**: Full reasoning quality analysis (5 signals)
- **`data_structs.h`**: Investigation, Alert, Escalation records as structs
- **`pybind11_module.cpp`**: Python bindings for C++ functions

### Key Algorithms to Convert
1. **Keyword classification** (parse_justification): unordered_set lookups
2. **Coherence scoring**: expected vs actual depth comparison
3. **Template detection**: string normalization + Counter equivalents
4. **Reasoning inflation**: depth >= 4 + coherence < 0.4
5. **4 signal functions**: shallow_justification, template_notes, missing_escalation_rationale, reasoning_inflation

### Performance Expectations
| Metric | Python | Target C++ | Improvement |
|--------|--------|------------|-------------|
| Per-CSE signal processing | ~1.8s | <0.1s | 18x |
| Full pipeline (50 CSEs) | ~90s | <5s | 18x |
| Memory per CSE | ~5MB | ~1MB | 5x reduction |

### Library Dependencies
- **pybind11**: Python/C++ bindings
- **nlohmann/json**: JSON parsing (header-only, replacement for pandas json ops)
- **fmt**: Formatting (replacement for manual string formatting)
- **optional**:Boost::unordered_set for keyword lookups (or std::unordered_set)

### Migration Roadmap

| Milestone | Description | Acceptance Criteria |
|-----------|-------------|---------------------|
| M1 | C++ kernel for `parse_justification` + `coherence_score` | Python outputs match C++ for 100 test cases |
| M2 | C++ kernel for `detect_template_notes` | Template ratio computation matches |
| M3 | C++ implementation of all 4 reasoning_quality signals | All 20 tests pass with C++ backend |
| M4 | Full pipeline benchmark: 50 CSEs in <10s | Performance target met |
| M5 | API compatibility: /api/report/{cse_id} returns same data | No regressions |

### Risk Mitigation
- **Parallel development**: Keep Python working while C++ is built
- **Golden test suite**: Save Python outputs, compare against C++ outputs
- **Incremental rollout**: Feature flag to switch between Python/C++ backends
- **Fallback**: Python backend active if C++ compilation fails

## Code Structure (Post-Conversion)

```
src/
  analytics/
    signal_kernels.hpp      # C++ header with inline functions
    reasoning_quality.hpp   # C++ reasoning quality analysis
    pybind11_module.cpp     # Python bindings
    # Python files keep existing API surface
  api/
    # FastAPI unchanged, delegates to backend
    
tests/
  # Existing Python tests continue to pass
  # New C++ verification tests
```

## Immediate Next Steps
1. Set up pybind11 build system (cmake + pybind11)
2. Convert `parse_justification` to C++ (keyword dict -> unordered_set)
3. Convert `coherence_score` to C++ (simple arithmetic)
4. Run golden test comparison
5. Convert remaining 4 signal functions iteratively
6. Benchmark full pipeline
7. Update CI/CD to run both backends

## Validation Requirements (from existing specs)
- All 8 original seeded weaknesses must remain detected
- New CSE-037 (shallow_reasoning) and CSE-048 (deep_reasoning) seeded
- Coverage: 100%
- Precision (signal): 100%
- Precision (literal): 94%
- False-positive rate: 0%
- Examiner alignment: 0.909