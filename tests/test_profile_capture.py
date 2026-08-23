import cProfile
import pstats
import io
from tests.test_capture_performance import TestCapturePerformance

def profile_capture_processing():
    """Profile the data capture processing function"""
    profiler = cProfile.Profile()
    profiler.enable()
    
    try:
        test_case = TestCapturePerformance()
        test_case.test_capture_processing_speed()
    except Exception as e:
        print(f"Error during profiling: {e}")
    
    profiler.disable()
    
    # Print statistics
    s = io.StringIO()
    stats = pstats.Stats(profiler, stream=s)
    stats.sort_stats(pstats.SortKey.CUMULATIVE)
    stats.print_stats(10)
    
    print("\n=== Top 10 most time-consuming functions ===")
    print(s.getvalue())
    
    return profiler

if __name__ == "__main__":
    profiler = profile_capture_processing()
    
    print("\n=== Detailed line-by-line profiling ===")
    import line_profiler
    lp = line_profiler.LineProfiler()
    
    try:
        from app.services.captured_form_processor import CapturedFormProcessor
        lp.add_function(CapturedFormProcessor.process_submission)
        lp.add_function(CapturedFormProcessor._map_data)
        lp.add_function(CapturedFormProcessor._validate)
        
        test_case = TestCapturePerformance()
        lp_wrapper = lp(test_case.test_capture_processing_speed)
        lp_wrapper()
        
        lp.print_stats()
    except ImportError as e:
        print(f"Line profiler not available: {e}")
        print("Install with: pip install line_profiler")
