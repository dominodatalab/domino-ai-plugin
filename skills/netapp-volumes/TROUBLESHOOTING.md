# NetApp Volumes troubleshooting

Symptoms and fixes for volumes missing at the mount path, permission errors, snapshot tag paths that do not appear, missing filesystems, and slow reads.

## Troubleshooting

### Volume Not Found at Mount Path
- Verify the volume is added to the project (**Data > NetApp Volumes**)
- Confirm the volume name matches the path exactly (case-sensitive)
- Check that the workspace/job was started after the volume was added to the project
- Restart the workspace to pick up newly added volumes

### Permission Denied
- Check your role on the volume (need Editor or Owner to write)
- Verify you have been granted access by the volume owner
- For read-only snapshots, use the snapshot tag path instead of the live volume path

### Snapshot Tag Not Mounted
- Each snapshot has at most **one** tag path — the most recently applied tag. Earlier tags on the same snapshot are never surfaced as directories and cannot be accessed by path.
- Tag paths for new snapshots do **not** appear in a running workspace. The numbered snapshot directory (`/snapshots/<name>/<number>/`) appears immediately, but the tag symlink path only becomes visible after restarting the workspace.
- Verify the tag was created successfully via the UI or API

### No NetApp Filesystems Available
- Contact your Domino administrator — they must register NetApp ONTAP filesystems before volumes can be created
- Admins can register filesystems via **Admin > NetApp Volumes**

### Slow Read Performance
- Use columnar formats (Parquet, Feather) instead of CSV for tabular data
- Read only needed columns: `pd.read_parquet(path, columns=["col1", "col2"])`
- Use Dask or chunked reading for files larger than available RAM
