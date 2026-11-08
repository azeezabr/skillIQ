"""Every search filter the frontend may send, taken from the TheirStack /v1/jobs/search docs.

To support a new filter, add its name here — nothing else changes. Anything not listed is rejected with a 422
rather than forwarded, so a typo can't silently widen (and bill for) a search.

NOT allowed from the frontend (server-owned): page, offset, cursor, order_by, include_total_results,
blur_company_data. `limit` is handled separately and clamped.
"""

ALLOWED_FILTERS = frozenset({
    # Dates
    "posted_at_max_age_days", "posted_at_gte", "posted_at_lte",
    "discovered_at_gte", "discovered_at_lte", "discovered_at_max_age_days", "discovered_at_min_age_days",
    "closed_at_gte", "closed_at_lte", "is_closed",
    # Identity / source
    "job_id_or", "job_id_not", "property_exists_or", "property_exists_and",
    "final_url_exists", "hiring_managers_exists", "company_linkedin_url_exists", "easy_apply",
    "url_domain_or", "url_domain_not", "scraper_name_pattern_or",
    # Job content
    "job_title_or", "job_title_not", "job_title_pattern_or", "job_title_pattern_and", "job_title_pattern_not",
    "job_description_contains_or", "job_description_contains_not",
    "job_seniority_or", "employment_statuses_or", "workplace_types_or", "remote",
    "job_technology_slug_or", "job_technology_slug_and", "job_technology_slug_not",
    "job_keyword_slug_or", "job_keyword_slug_and", "job_keyword_slug_not",
    # Job location
    "job_country_code_or", "job_country_code_not", "job_location_or", "job_location_not",
    "job_location_pattern_or", "job_location_pattern_not",
    # Salary
    "min_salary_usd", "max_salary_usd",
    # Company
    "company_id_or", "company_id_not", "company_domain_or", "company_domain_not",
    "company_name_or", "company_name_not", "company_name_case_insensitive_or",
    "company_name_partial_match_or", "company_name_partial_match_not",
    "company_linkedin_url_or", "company_list_id_or", "company_list_id_not", "company_type",
    "company_country_code_or", "company_country_code_not", "company_country_code_not_or_null",
    "company_location_pattern_or", "company_description_pattern_or", "company_description_pattern_not",
    "company_description_pattern_accent_insensitive",
    "industry_id_or", "industry_id_not", "industry_id_not_or_null",
    "company_tags_or", "company_investors_or", "company_investors_partial_match_or",
    "funding_stage_or", "last_funding_round_date_gte", "last_funding_round_date_lte",
    "min_funding_usd", "max_funding_usd",
    "min_revenue_usd", "max_revenue_usd", "min_revenue_usd_or_null", "max_revenue_usd_or_null",
    "min_employee_count", "max_employee_count", "min_employee_count_or_null", "max_employee_count_or_null",
    "only_yc_companies",
    "company_technology_slug_or", "company_technology_slug_and", "company_technology_slug_not",
    "company_keyword_slug_or", "company_keyword_slug_and", "company_keyword_slug_not",
    "company_crm_status_or", "company_crm_status_not", "revealed_company_data",
})

# TheirStack rejects a search unless at least one of these is present.
REQUIRED_ONE_OF = frozenset({
    "posted_at_max_age_days", "posted_at_gte", "posted_at_lte", "job_id_or", "company_id_or",
    "company_domain_or", "company_linkedin_url_or", "company_name_or",
    "company_name_case_insensitive_or", "company_name_partial_match_or",
})
