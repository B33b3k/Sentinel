// Sprint 7 fallback query placeholder.
// Detects fan-in/fan-out account movement once transaction relationships are loaded.
MATCH (source:Account)-[:SENT]->(inbound:Transaction)-[:TO]->(mule:Account)
MATCH (mule)-[:SENT]->(outbound:Transaction)-[:TO]->(destination:Account)
WHERE source <> destination
RETURN mule.account_id AS mule_account_id,
       count(DISTINCT source) AS source_count,
       count(DISTINCT destination) AS destination_count,
       collect(DISTINCT source.account_id)[0..10] AS sample_sources
ORDER BY source_count DESC, destination_count DESC;
