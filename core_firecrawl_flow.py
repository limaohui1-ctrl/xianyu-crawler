"""Firecrawl collection orchestration helpers.

This module keeps Firecrawl-specific flow logic out of the large collector
class while letting the existing collector own storage, progress, and fallback.
"""

from core_database import content_fingerprint
from core_firecrawl import (
    firecrawl_document_to_record,
    merge_firecrawl_extract_record,
    merge_firecrawl_interact_record,
)
from core_urls import normalize_url, url_domain


def expand_pages_with_firecrawl_map(url, firecrawl_client, page_limit, logger=None, record_error=None):
    start_url = normalize_url(url)
    if not start_url:
        return []
    root_domain = url_domain(start_url)
    try:
        raw_links = firecrawl_client.map(start_url)
    except Exception as exc:
        if record_error:
            record_error(
                "Firecrawl Map 失败，已保留当前网址",
                exc,
                logger=logger,
                details={"url": start_url},
            )
        return [start_url]

    urls = [start_url]
    seen = {start_url}
    for item in raw_links or []:
        if isinstance(item, dict):
            raw_url = item.get("url") or item.get("href") or ""
        else:
            raw_url = str(item or "")
        link_url = normalize_url(raw_url, start_url)
        if not link_url or link_url in seen:
            continue
        if root_domain and url_domain(link_url) != root_domain:
            continue
        urls.append(link_url)
        seen.add(link_url)
        if len(urls) >= max(1, int(page_limit or 1)):
            break

    if logger:
        if len(urls) > 1:
            logger(f"Firecrawl Map 发现 {len(urls)} 个同站链接：{'; '.join(urls[:8])}")
        else:
            logger("Firecrawl Map 未发现更多同站链接，保留当前网址。")
    return urls


def expand_urls_with_firecrawl_search(urls, firecrawl_client, firecrawl_config, logger=None, record_error=None):
    expanded = []
    seen = set()
    for item in urls or []:
        normalized = normalize_url(item)
        if normalized and normalized not in seen:
            expanded.append(normalized)
            seen.add(normalized)
    try:
        search_results = firecrawl_client.search(
            firecrawl_config.search_query,
            limit=firecrawl_config.search_limit,
            sources=firecrawl_config.search_sources,
        )
    except Exception as exc:
        if record_error:
            record_error(
                "Firecrawl Search 失败，已保留原始网址队列",
                exc,
                logger=logger,
                details={"query": firecrawl_config.search_query},
            )
        return expanded

    added = []
    for item in search_results or []:
        url = normalize_url(item.get("url", "") if isinstance(item, dict) else item)
        if url and url not in seen:
            expanded.append(url)
            added.append(url)
            seen.add(url)
        if len(added) >= int(firecrawl_config.search_limit or 5):
            break

    if logger:
        if added:
            logger(f"Firecrawl Search 扩展 {len(added)} 个候选网址：{'; '.join(added[:8])}")
        else:
            logger("Firecrawl Search 未扩展出新的候选网址。")
    return expanded


def collect_with_firecrawl_crawl(
    urls,
    firecrawl_client,
    choose_template,
    template_name,
    scroll_times,
    run_id,
    skip_unchanged,
    database,
    results,
    progress,
    emit_progress,
    record_from_document,
    stop_requested=None,
    logger=None,
    record_error=None,
):
    fallback_urls = []
    completed_count = 0
    for raw_url in urls:
        if stop_requested and stop_requested():
            break
        url = normalize_url(raw_url)
        if not url:
            continue
        emit_progress("Firecrawl Crawl", url)
        template = choose_template(url, template_name)
        template.scroll_times = scroll_times
        try:
            crawl_payload = firecrawl_client.crawl(url)
            crawl_docs = crawl_payload.get("data") or []
            if not crawl_docs:
                fallback_urls.append(url)
                continue
            progress["total"] = max(progress["total"], progress["processed"] + len(crawl_docs))
            if logger:
                logger(
                    f"Firecrawl Crawl 完成：{url}，"
                    f"{crawl_payload.get('completed', len(crawl_docs))}/{crawl_payload.get('total', len(crawl_docs))}。"
                )
            for document in crawl_docs:
                if stop_requested and stop_requested():
                    break
                record = record_from_document(document, url, template, firecrawl_client)
                record["run_id"] = int(run_id or 0)
                database.save_record(record, skip_unchanged=skip_unchanged)
                results.append(record)
                completed_count += 1
                emit_progress(
                    "Firecrawl Crawl 页面完成",
                    record.get("url", url),
                    increment=True,
                    failed=bool(record.get("error")),
                )
        except Exception as exc:
            if record_error:
                record_error(
                    "Firecrawl Crawl 失败，已改用普通采集",
                    exc,
                    logger=logger,
                    details={"url": url},
                )
            fallback_urls.append(url)
    return {
        "completed_all": completed_count > 0 and not fallback_urls,
        "fallback_urls": fallback_urls,
    }


def collect_with_firecrawl_batch(
    urls,
    firecrawl_client,
    choose_template,
    template_name,
    scroll_times,
    run_id,
    skip_unchanged,
    database,
    results,
    progress,
    emit_progress,
    record_from_document,
    stop_requested=None,
    logger=None,
    record_error=None,
):
    batch_urls = []
    seen_batch_urls = set()
    for raw_url in urls:
        normalized = normalize_url(raw_url)
        if normalized and normalized not in seen_batch_urls:
            batch_urls.append(normalized)
            seen_batch_urls.add(normalized)
    if len(batch_urls) <= 1:
        return False

    try:
        emit_progress("Firecrawl Batch")
        batch_payload = firecrawl_client.batch_scrape(batch_urls)
        batch_docs = batch_payload.get("data") or []
        if batch_docs:
            progress["total"] = max(progress["total"], progress["processed"] + len(batch_docs))
            if logger:
                logger(
                    f"Firecrawl Batch 完成："
                    f"{batch_payload.get('completed', len(batch_docs))}/{batch_payload.get('total', len(batch_docs))}。"
                )
            template = choose_template(batch_urls[0], template_name)
            template.scroll_times = scroll_times
            for document in batch_docs:
                if stop_requested and stop_requested():
                    break
                fallback_url = document.get("url") if isinstance(document, dict) else batch_urls[0]
                record = record_from_document(document, fallback_url, template, firecrawl_client)
                record["run_id"] = int(run_id or 0)
                database.save_record(record, skip_unchanged=skip_unchanged)
                results.append(record)
                emit_progress(
                    "Firecrawl Batch 页面完成",
                    record.get("url", ""),
                    increment=True,
                    failed=bool(record.get("error")),
                )
            return True
        if logger:
            logger("Firecrawl Batch 未返回页面数据，继续普通采集。")
    except Exception as exc:
        if record_error:
            record_error(
                "Firecrawl Batch 失败，已改用普通采集",
                exc,
                logger=logger,
                details={"url_count": len(batch_urls)},
            )
    return False


def collect_one_firecrawl(
    url,
    template,
    firecrawl_client,
    logger=None,
    compact_text=None,
    assess_record_completeness=None,
    record_error=None,
):
    if logger:
        logger(f"Firecrawl 开始采集：{url}")
    document = firecrawl_client.scrape(url)
    record = record_from_firecrawl_document(
        document,
        url,
        template,
        firecrawl_client=firecrawl_client,
        logger=logger,
        compact_text=compact_text,
        assess_record_completeness=assess_record_completeness,
        record_error=record_error,
    )
    if logger:
        title = record.get("title") or url
        logger(f"Firecrawl 采集完成：{compact_text(title, 80) if compact_text else title}")
    return record


def record_from_firecrawl_document(
    document,
    fallback_url,
    template,
    firecrawl_client=None,
    logger=None,
    compact_text=None,
    assess_record_completeness=None,
    record_error=None,
):
    record = firecrawl_document_to_record(document, fallback_url, template_name=template.name)
    if firecrawl_client and firecrawl_client.config.use_extract:
        record_url = record.get("url") or fallback_url
        if logger:
            logger(f"Firecrawl 开始结构化抽取：{record_url}")
        try:
            extract_payload = firecrawl_client.extract([record_url])
            record = merge_firecrawl_extract_record(record, extract_payload)
            if logger:
                title = record.get("title") or fallback_url
                logger(f"Firecrawl 结构化抽取完成：{compact_text(title, 80) if compact_text else title}")
        except Exception as exc:
            if record_error:
                record_error(
                    "Firecrawl Extract 失败，已保留 scrape 结果",
                    exc,
                    logger=logger,
                    details={"url": record_url},
                )

    if firecrawl_client and firecrawl_client.config.use_interact:
        job_id = ""
        if isinstance(document, dict):
            job_id = document.get("firecrawl_job_id") or document.get("jobId") or document.get("job_id") or ""
        if job_id:
            record_url = record.get("url") or fallback_url
            if logger:
                logger(f"Firecrawl 开始交互：{record_url}")
            try:
                interact_payload = firecrawl_client.interact(job_id)
                record = merge_firecrawl_interact_record(record, interact_payload)
                if logger:
                    title = record.get("title") or fallback_url
                    logger(f"Firecrawl 交互完成：{compact_text(title, 80) if compact_text else title}")
            except Exception as exc:
                if record_error:
                    record_error(
                        "Firecrawl Interact 失败，已保留 scrape 结果",
                        exc,
                        logger=logger,
                        details={"url": record_url, "job_id": job_id},
                    )
        elif logger:
            logger("Firecrawl Interact 已开启，但当前 scrape 响应没有 job id，已跳过交互。")

    if assess_record_completeness:
        completeness = assess_record_completeness(record)
        record["completeness_score"] = completeness["score"]
        record["completeness_label"] = completeness["label"]
        record["completeness_missing"] = completeness["missing"]
    record["fingerprint"] = content_fingerprint(record)
    return record
