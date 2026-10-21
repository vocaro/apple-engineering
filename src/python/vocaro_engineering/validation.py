"""Validate report coverage against the exact input manifest, independently of its domain."""
import hashlib

def validate_reports(raw, manifest, native, reference):
    digest = hashlib.sha256(raw).hexdigest()
    ids = [c['id'] for c in manifest['cases']]
    if len(set(ids)) != len(ids): raise ValueError('Duplicate manifest IDs')
    for report in (native, reference):
        if report['manifestSHA256'] != digest:
            raise ValueError('Report does not describe the supplied manifest')
        reported = [c['id'] for c in report['cases']]
        if len(set(reported)) != len(reported) or set(reported) != set(ids):
            raise ValueError('Report must contain each manifest ID exactly once')
