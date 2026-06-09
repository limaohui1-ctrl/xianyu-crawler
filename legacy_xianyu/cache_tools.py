import os
import shutil


def chrome_cache_targets(profile_dir):
    profile_dir = os.path.abspath(profile_dir)
    relative_targets = [
        os.path.join("Default", "Cache"),
        os.path.join("Default", "Code Cache"),
        os.path.join("Default", "GPUCache"),
        os.path.join("Default", "DawnCache"),
        os.path.join("Default", "Service Worker", "CacheStorage"),
        "ShaderCache",
        "GrShaderCache",
        "GraphiteDawnCache",
        "BrowserMetrics",
        "Crashpad",
    ]
    return [os.path.join(profile_dir, relative_path) for relative_path in relative_targets]


def clear_chrome_cache(profile_dir):
    profile_dir = os.path.abspath(profile_dir)
    removed_count = 0
    failed_paths = []
    for cache_path in chrome_cache_targets(profile_dir):
        cache_path = os.path.abspath(cache_path)
        try:
            common_path = os.path.commonpath([profile_dir, cache_path])
        except Exception:
            common_path = ""
        if common_path != profile_dir:
            failed_paths.append(f"{cache_path}：路径越界，已跳过")
            continue
        if not os.path.exists(cache_path):
            continue
        try:
            if os.path.isdir(cache_path):
                shutil.rmtree(cache_path)
            else:
                os.remove(cache_path)
            removed_count += 1
        except Exception as exc:
            failed_paths.append(f"{cache_path}：{exc}")
    return removed_count, failed_paths
