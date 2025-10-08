# HTML Parsing vs Data File Parsing - Performance Analysis

## Question
Would it be faster to parse the static HTML file to extract data rather than re-parsing the original data files when loading the dashboard a second time?

## Short Answer
**No, parsing the HTML would likely be SLOWER and more complex than the current approach.**

## Detailed Analysis

### Current Data Flow

1. **Data Files → Parser → DataFrames → Bokeh ColumnDataSource → HTML**
   - CSV/TXT files parsed by specialized parsers (Svan, NTi, Noise Sentry)
   - Data converted to pandas DataFrames
   - DataFrames fed into Bokeh `ColumnDataSource` objects
   - Bokeh serializes ColumnDataSource data as JSON within the HTML
   - `file_html()` generates a single self-contained HTML file

### What's Actually in the HTML

When Bokeh generates static HTML via `file_html()`, it:
- Embeds all `ColumnDataSource` data as **JSON arrays** within `<script>` tags
- Includes all Bokeh JavaScript libraries (either via CDN or inline)
- Stores the complete Bokeh document structure (models, layouts, etc.)
- The data is **serialized** in Bokeh's internal format, not in a user-friendly structure

### Why HTML Parsing Would Be Slower

#### 1. **Data is Already Optimized in Original Format**
- CSV/TXT files are already optimized for parsing
- Pandas `read_csv()` is highly optimized C code
- Your parsers are already efficient and handle edge cases

#### 2. **HTML Parsing Complexity**
```
Original:  CSV → pandas DataFrame (1 step, optimized)
HTML:      HTML → Extract JSON → Parse JSON → Reconstruct DataFrames (3+ steps)
```

#### 3. **Data Extraction Challenges**
- Need to parse HTML to find the correct `<script>` tags
- Extract JSON from JavaScript code (not straightforward)
- Bokeh's JSON format is designed for Bokeh models, not for data extraction
- Multiple ColumnDataSources with complex nested structures
- Need to reverse-engineer which data belongs to which position/chart
- Spectral data is pre-processed and padded for visualization, not raw data

#### 4. **Loss of Metadata**
- Original parsers extract important metadata (sample periods, data profiles, etc.)
- HTML only contains the final processed data for visualization
- You'd lose the ability to reprocess data differently

#### 5. **Maintenance Burden**
- HTML structure could change with Bokeh version updates
- Fragile parsing logic that breaks easily
- Original parsers are already tested and reliable

### Performance Bottlenecks in Current System

Based on the code review, the actual bottlenecks are likely:

1. **File I/O** - Reading large CSV files from disk
2. **Datetime Parsing** - Converting strings to timezone-aware datetime objects
3. **Data Merging** - Combining multiple files for the same position
4. **Spectral Data Processing** - Padding and preparing spectrogram data

### Better Optimization Strategies

Instead of parsing HTML, consider these approaches:

#### Option 1: **Pickle Cache** (Recommended)
```python
# After parsing, save processed DataFrames
import pickle

cache_file = config_path.replace('.json', '_cache.pkl')
if os.path.exists(cache_file):
    # Load from cache
    with open(cache_file, 'rb') as f:
        position_data = pickle.load(f)
else:
    # Parse original files
    position_data = parse_all_files()
    # Save to cache
    with open(cache_file, 'wb') as f:
        pickle.dump(position_data, f)
```

**Advantages:**
- 10-100x faster than re-parsing CSVs
- Preserves all DataFrame structure and metadata
- Simple to implement
- Can invalidate cache based on file modification times

#### Option 2: **Parquet Files**
```python
# Convert CSVs to Parquet format (columnar, compressed)
parquet_file = original_file.replace('.csv', '.parquet')
if os.path.exists(parquet_file):
    df = pd.read_parquet(parquet_file)
else:
    df = parse_csv(original_file)
    df.to_parquet(parquet_file)
```

**Advantages:**
- Much faster than CSV parsing
- Smaller file sizes (compressed)
- Preserves data types (no re-parsing needed)
- Industry standard for data science

#### Option 3: **HDF5 Storage**
```python
# Store all position data in a single HDF5 file
with pd.HDFStore('survey_data.h5') as store:
    store['north/overview'] = north_overview_df
    store['north/log'] = north_log_df
    # etc.
```

**Advantages:**
- Very fast random access
- Can store multiple DataFrames in one file
- Good for large datasets

#### Option 4: **Lazy Loading**
- Only load data for visible time ranges
- Stream data as user pans/zooms
- More complex but scales to very large datasets

### Recommended Implementation

**Phase 1: Add Pickle Caching**
```python
# In data_manager.py
class DataManager:
    def __init__(self, source_configurations, use_cache=True):
        self.cache_enabled = use_cache
        cache_key = self._generate_cache_key(source_configurations)
        cache_file = Path(f".cache/{cache_key}.pkl")
        
        if use_cache and cache_file.exists():
            if self._is_cache_valid(cache_file, source_configurations):
                logger.info("Loading from cache...")
                self._load_from_cache(cache_file)
                return
        
        # Normal parsing
        self._parse_all_sources(source_configurations)
        
        if use_cache:
            self._save_to_cache(cache_file)
    
    def _is_cache_valid(self, cache_file, sources):
        """Check if cache is newer than all source files"""
        cache_mtime = cache_file.stat().st_mtime
        for source in sources:
            if Path(source['path']).stat().st_mtime > cache_mtime:
                return False
        return True
```

**Phase 2: Add Progress Indicators**
- Show parsing progress to user
- Makes perceived performance better even if actual speed is the same

**Phase 3: Consider Parquet for Very Large Datasets**
- Only if you have surveys with millions of rows
- Converts CSV → Parquet on first load

### Benchmarking Estimates

For a typical survey with 3 positions, 7 days of data at 1-second intervals:

| Method | Time | Complexity |
|--------|------|------------|
| Parse CSV (current) | ~5-10s | Low |
| Parse HTML | ~15-30s | High |
| Load Pickle cache | ~0.5-1s | Low |
| Load Parquet | ~1-2s | Medium |

### Conclusion

**Do NOT parse the HTML.** Instead:

1. ✅ Implement pickle caching for ~10x speedup
2. ✅ Add cache invalidation based on file modification times
3. ✅ Show loading progress to improve perceived performance
4. ❌ Don't parse HTML - it's slower and more fragile

The HTML file is optimized for **viewing**, not for **data extraction**. The original data files are the source of truth and should remain the primary input for the dashboard.
