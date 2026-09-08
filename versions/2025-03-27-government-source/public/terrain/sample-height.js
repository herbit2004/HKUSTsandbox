/** Return metres HKPD, or null when outside source-supported terrain.
 * Grid JSON samples run east across each row and south down successive rows.
 * This helper interpolates existing source-supported samples for marker height;
 * it does not create additional survey evidence or fill coastal NoData.
 */
export function sampleTerrainHeight(grid, easting, northing) {
  const col = (easting - grid.first_easting) / grid.easting_step;
  const row = (northing - grid.first_northing) / grid.northing_step;
  if (!Number.isFinite(col) || !Number.isFinite(row) || col < 0 || row < 0 || col > grid.columns-1 || row > grid.rows-1) return null;
  const c0 = Math.min(Math.floor(col),grid.columns-2);
  const r0 = Math.min(Math.floor(row),grid.rows-2);
  const tx = col-c0, ty = row-r0, i = r0*grid.columns+c0;
  const a=grid.heights[i], b=grid.heights[i+1], c=grid.heights[i+grid.columns], d=grid.heights[i+grid.columns+1];
  if ([a,b,c,d].some(v => v === null || !Number.isFinite(v))) return null;
  return (a*(1-tx)+b*tx)*(1-ty)+(c*(1-tx)+d*tx)*ty;
}

export function sampleTerrainLocalHeight(grid, x, z) {
  return sampleTerrainHeight(grid, x + grid.origin.easting, grid.origin.northing - z);
}
