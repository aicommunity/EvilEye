"""
Constants for object detector module.
All magic numbers and default values are defined here.
"""

# Queue sizes
DEFAULT_INPUT_QUEUE_SIZE = 10
DEFAULT_THREAD_QUEUE_SIZE = 2

# Default parameters
DEFAULT_STRIDE = 1
DEFAULT_NUM_DETECTION_THREADS = 3
DEFAULT_CONFIDENCE = 0.25
DEFAULT_INFERENCE_SIZE = 640

# Timeouts (in seconds)
MODEL_PRELOAD_TIMEOUT = 0.2
MODEL_READY_TIMEOUT = 30.0
PROCESSING_SLEEP_INTERVAL = 0.01
THREAD_START_DELAY = 0.1

# Background subtraction defaults
DEFAULT_BG_HISTORY = 500
DEFAULT_BG_VAR_THRESHOLD = 16.0
DEFAULT_BG_DETECT_SHADOWS = True

# Frame freshness and batching
DEFAULT_MAX_FRAME_AGE_MS = 500  # Maximum age of frame before dropping (milliseconds)
DEFAULT_BATCH_SIZE = 4  # Default batch size for batching (optional, None = disabled)
DEFAULT_BATCH_TIMEOUT_MS = 16  # Timeout for forming a batch (milliseconds)

# Frame freshness and batching
DEFAULT_MAX_FRAME_AGE_MS = 500  # Maximum age of frame before dropping (milliseconds)
DEFAULT_BATCH_SIZE = 4  # Default batch size for batching (optional, None = disabled)
DEFAULT_BATCH_TIMEOUT_MS = 16  # Timeout for forming a batch (milliseconds)

"""
Constants for object detector module.
All magic numbers and default values are defined here.
"""

# Queue sizes
DEFAULT_INPUT_QUEUE_SIZE = 10
DEFAULT_THREAD_QUEUE_SIZE = 2

# Default parameters
DEFAULT_STRIDE = 1
DEFAULT_NUM_DETECTION_THREADS = 3
DEFAULT_CONFIDENCE = 0.25
DEFAULT_INFERENCE_SIZE = 640

# Timeouts (in seconds)
MODEL_PRELOAD_TIMEOUT = 0.2
MODEL_READY_TIMEOUT = 30.0
PROCESSING_SLEEP_INTERVAL = 0.01
THREAD_START_DELAY = 0.1

# Background subtraction defaults
DEFAULT_BG_HISTORY = 500
DEFAULT_BG_VAR_THRESHOLD = 16.0
DEFAULT_BG_DETECT_SHADOWS = True

# Frame freshness and batching
DEFAULT_MAX_FRAME_AGE_MS = 500  # Maximum age of frame before dropping (milliseconds)
DEFAULT_BATCH_SIZE = 4  # Default batch size for batching (optional, None = disabled)
DEFAULT_BATCH_TIMEOUT_MS = 16  # Timeout for forming a batch (milliseconds)
