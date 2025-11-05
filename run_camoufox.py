import multiprocessing
import os
import time

from browser.instance import run_browser_instance
from utils.logger import setup_logging
from utils.paths import cookies_dir, logs_dir


def _clean_env_value(raw):
    if raw is None:
        return None
    stripped = raw.strip()
    return stripped or None


def load_instances_from_env(logger):
    """
    解析环境变量，自动从 cookies/ 目录扫描文件，为每个文件创建一个实例。
    """
    # 1. 读取所有实例共享的URL
    shared_url = _clean_env_value(os.getenv("CAMOUFOX_INSTANCE_URL"))
    if not shared_url:
        logger.error("错误: 缺少环境变量 CAMOUFOX_INSTANCE_URL。所有实例需要一个共享的目标URL。")
        return None, None

    # 2. 读取全局设置
    global_settings = {
        "headless": _clean_env_value(os.getenv("CAMOUFOX_HEADLESS")) or "virtual",
        "url": shared_url  # 所有实例都使用这个URL
    }

    proxy_value = _clean_env_value(os.getenv("CAMOUFOX_PROXY"))
    if proxy_value:
        global_settings["proxy"] = proxy_value

    # 3. 扫描 cookies 目录
    try:
        cookie_path = cookies_dir()
        if not os.path.isdir(cookie_path):
            logger.error(f"错误: cookies 目录不存在: {cookie_path}")
            return None, None

        # 列出所有 .json 文件
        cookie_files = [f for f in os.listdir(cookie_path) if f.lower().endswith('.json')]

        if not cookie_files:
            logger.error(f"错误: 在 {cookie_path} 目录下未找到任何 .json 格式的 cookie 文件。")
            return None, None

    except Exception as e:
        logger.error(f"扫描 cookies 目录时出错: {e}")
        return None, None

    # 4. 为每个 cookie 文件创建实例配置
    instances = [{"cookie_file": f} for f in cookie_files]

    logger.info(f"在 {cookie_path} 中找到 {len(instances)} 个 cookie 文件，将为每个文件启动一个实例。")
    logger.info(f"所有实例将访问同一个 URL: {shared_url}")

    return global_settings, instances


def main():
    """
    主函数，读取环境变量并为每个实例启动一个独立的浏览器进程。
    """
    log_dir = logs_dir()
    os.makedirs(log_dir, exist_ok=True)
    os.makedirs(cookies_dir(), exist_ok=True)

    logger = setup_logging(str(log_dir / 'app.log'))

    logger.info("---------------------Camoufox 实例管理器开始启动---------------------")

    global_settings, instance_profiles = load_instances_from_env(logger)
    if not instance_profiles:
        logger.error("错误: 环境变量中未找到任何实例配置。")
        return

    processes = []
    for i, profile in enumerate(instance_profiles, 1):
        final_config = global_settings.copy()
        final_config.update(profile)

        if 'cookie_file' not in final_config or 'url' not in final_config:
            logger.warning(f"警告: 跳过一个无效的配置项 (缺少 cookie_file 或 url): {profile}")
            continue

        cookie_candidate = final_config['cookie_file']
        if os.path.basename(cookie_candidate) != cookie_candidate:
            logger.error(
                f"错误: cookie_file 只能提供文件名，不允许携带路径: {cookie_candidate}"
            )
            continue

        if not cookie_candidate.lower().endswith('.json'):
            logger.error(
                f"错误: cookie_file 必须是 .json 文件: {cookie_candidate}"
            )
            continue

        cookies_root = cookies_dir().resolve()
        resolved_cookie = (cookies_root / cookie_candidate).resolve()
        if cookies_root not in resolved_cookie.parents and resolved_cookie != cookies_root:
            logger.error(
                f"错误: cookie_file 必须位于 cookies/ 目录下: {cookie_candidate}"
            )
            continue

        logger.info(f"正在启动第 {i}/{len(instance_profiles)} 个浏览器实例 (cookie: {cookie_candidate})...")
        process = multiprocessing.Process(target=run_browser_instance, args=(final_config,))
        processes.append(process)
        process.start()

        # 如果不是最后一个实例，等待30秒再启动下一个实例，避免并发启动导致的高CPU占用
        if i < len(instance_profiles):
            logger.info(f"等待 30 秒后启动下一个实例...")
            time.sleep(30)

    if not processes:
        logger.error("错误: 没有有效的实例配置可以启动。")
        return

    logger.info(f"所有 {len(processes)} 个浏览器实例已启动完成。按 Ctrl+C 终止所有实例。")

    try:
        for process in processes:
            process.join()
    except KeyboardInterrupt:
        logger.info("捕获到 Ctrl+C, 正在终止所有子进程...")
        for process in processes:
            process.terminate()
            process.join()
        logger.info("所有进程已终止。")

if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
