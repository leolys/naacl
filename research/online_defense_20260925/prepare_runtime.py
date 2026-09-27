"""Create an isolated original-runtime copy with two verified missing assets."""
from pathlib import Path
import shutil
import sys
from deps import HERE, SNAPSHOT, wire

RECOVERED = {
    'p005_texas_red.jpeg': ('web_agent_benchmark/public_shell/assets/p005_texas_red.jpeg',
        '7bacf4de09d530f34aab7f5a8363583de0cfd86f571b300a5e6da4b695a849d1'),
    'clean.png': ('web_agent_benchmark/clean_benchmark_v1/assets/pub005/clean.png',
        '5ad8423233b02d6ca1c42237a3426b4e704d7eb6d4fb4f51c3e96cc5688bc0ad')}


def main():
    target = HERE / 'runtime_snapshot'
    if target.exists():
        raise ValueError('Refuse to overwrite a prepared runtime')
    for name, (_, digest) in RECOVERED.items():
        if wire.digest(HERE / 'asset_recovery' / name) != digest:
            raise ValueError('recovered_asset_does_not_match_readonly_server_probe')
    shutil.copytree(SNAPSHOT, target)
    recovery=[]
    for name, (relative, digest) in RECOVERED.items():
        dest=target/relative
        if dest.exists():raise ValueError('recovery_target_was_not_missing')
        dest.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(HERE/'asset_recovery'/name,dest)
        recovery.append({'remote':'/mnt/data/lys/CognitiveHijacking_CognitiveDenial/'+relative,
                         'local':str(dest),'sha256':digest,'source':'readonly SSH then SCP; no remote write'})
    original={str(p.relative_to(SNAPSHOT)):wire.digest(p) for p in SNAPSHOT.rglob('*') if p.is_file()}
    unchanged=all(wire.digest(target/p)==digest for p,digest in original.items())
    wire.dump(HERE/'asset_recovery/provenance.json',{'restored':recovery,'all_existing_files_unchanged':unchanged,
        'existing_file_count':len(original),'old_snapshot_not_modified':True,
        'pub005_actual_runtime_override_differs_from_spec_figure':True,
        'spec_official_figure_sha256':'e4390a1c4d8f62ac93ed20eba7da3dc6a1ff5e6aa36cac163c34dd5f229e8c81'})
    if not unchanged:raise ValueError('existing_file_difference')
    # New process only: original module bytes are unchanged, its filesystem root
    # is this isolated mirror. No live panel process is modified.
    sys.path.insert(0,str(target))
    import original_env
    original_env.SNAPSHOT=target
    from checks import audit_all
    output=HERE/'asset_check_v2'
    output.mkdir(exist_ok=False)
    rows=audit_all(output)
    print('Original routes available:',sum(r['status']=='supported_original_routes' for r in rows),'/',len(rows),flush=True)


if __name__=='__main__':main()
