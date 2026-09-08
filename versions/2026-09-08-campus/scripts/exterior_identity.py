"""Canonical owner validation shared by exterior integration/sync/source QA."""
import re


def exterior_entity_id(bundle):
    explicit, legacy = bundle.get('entityId'), bundle.get('buildingId')
    if explicit is not None and (not isinstance(explicit, str) or not re.fullmatch(r'[a-z][a-z0-9_]*:\S+', explicit)):
        raise ValueError('Invalid exterior entityId: '+str(bundle.get('id')))
    if legacy is not None and (not isinstance(legacy, str) or not legacy or re.search(r'\s', legacy)):
        raise ValueError('Invalid exterior buildingId: '+str(bundle.get('id')))
    if explicit and legacy and explicit != 'building:'+legacy:
        raise ValueError('Conflicting exterior entityId/buildingId: '+str(bundle.get('id')))
    owner = explicit or ('building:'+legacy if legacy else None)
    if not owner:
        raise ValueError('Missing exterior owner: '+str(bundle.get('id')))
    return owner


def validate_exterior_identities(bundles):
    ids, domains = set(), set()
    for bundle in bundles:
        exterior_entity_id(bundle)
        key = bundle.get('id')
        if not key or key in ids:
            raise ValueError('Duplicate exterior bundle ID: '+str(key))
        ids.add(key)
        domain = bundle.get('physicalDomainId')
        if domain is not None:
            if not isinstance(domain, str) or not domain or domain in domains:
                raise ValueError('Duplicate or empty exterior physical domain: '+str(key))
            domains.add(domain)
