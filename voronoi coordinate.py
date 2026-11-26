import argparse
import csv
from collections import Counter
from pathlib import Path
import re

import numpy as np
from scipy.spatial import cKDTree, ConvexHull

SEARCH_REGION = "global"  # global or mercator
MERCATOR_LATITUDE_LIMIT = 85.0
GREAT_CIRCLE_SAMPLES = 1300
FARTHEST_POINT_ACCURACY = 0
EARTH_RADIUS = 6371.0
POINT_PATTERN = re.compile(
    r'POINT\s*\(\s*([-+]?[0-9]*\.?[0-9]+)\s+([-+]?[0-9]*\.?[0-9]+)\s*\)')


def read_coordinates(filename):
    with open(filename, encoding="utf-8-sig") as file:
        coords = [(float(m.group(2)), float(m.group(1)))
                  for line in file if (m := POINT_PATTERN.search(line))]
    if not coords:
        raise ValueError('No POINT coordinates found')
    coords = np.asarray(coords, dtype=float)
    if not np.isfinite(coords).all() or np.any(np.abs(coords[:, 0]) > 90):
        raise ValueError("Invalid geographic coordinates")
    return np.radians(coords)


def find_farthest(coords, accuracy=FARTHEST_POINT_ACCURACY, samples=GREAT_CIRCLE_SAMPLES, search_region=SEARCH_REGION):
    if search_region not in ("global", "mercator"):
        raise ValueError("SEARCH_REGION must be global or mercator")
    limit = np.sin(np.radians(MERCATOR_LATITUDE_LIMIT)
                   ) if search_region == "mercator" else 1.0
    lat, lon = np.asarray(coords).T
    c = np.cos(lat)
    sites = np.column_stack((c*np.cos(lon), c*np.sin(lon), np.sin(lat)))
    sites = np.unique(np.round(sites, 14), axis=0)
    sites /= np.linalg.norm(sites, axis=1)[:, None]
    n = len(sites)
    if samples < 1 or accuracy < 0:
        raise ValueError('Invalid sample count or accuracy')
    if n == 2 and np.linalg.norm(sites.sum(axis=0)) < 1e-12:
        axis = sites[0]
        angles = np.linspace(-np.pi, np.pi, samples, endpoint=False)
        if np.linalg.norm(axis[:2]) < 1e-12:
            return np.column_stack((np.zeros(samples), np.degrees(angles)))
        u = np.cross(axis, np.eye(3)[np.argmin(np.abs(axis))])
        u /= np.linalg.norm(u)
        v = np.cross(axis, u)
        circle = np.cos(angles)[:, None]*u + np.sin(angles)[:, None]*v
        if search_region == "mercator":
            circle = circle[np.abs(circle[:, 2]) <= limit + 1e-12]
            # Include exact intersections with the latitude limits.
            amplitude = np.hypot(u[2], v[2])
            if amplitude > limit:
                phase = np.arctan2(v[2], u[2])
                t = np.array([phase + sign*np.arccos(z/amplitude)
                             for z in (-limit, limit) for sign in (-1, 1)])
                circle = np.vstack(
                    (circle, np.cos(t)[:, None]*u + np.sin(t)[:, None]*v))
        x, y, z = circle.T
        return np.degrees(np.column_stack((np.arctan2(z, np.hypot(x, y)), np.arctan2(y, x))))
    if n == 1 and search_region == "mercator" and np.linalg.norm(sites[0, :2]) < 1e-12:
        return np.column_stack((np.full(samples, -np.sign(sites[0, 2])*MERCATOR_LATITUDE_LIMIT), np.linspace(-180, 180, samples, endpoint=False)))
    centered = sites - sites[0]
    _, s, basis = np.linalg.svd(centered, full_matrices=False)
    rank = np.count_nonzero(s > 1e-12)
    candidates = []
    edges = np.empty((0, 2), dtype=int)
    if rank == 3:
        hull = ConvexHull(sites)
        candidates.append(hull.equations[:, :3])
        if search_region == "mercator" or np.any(hull.equations[:, 3] >= -1e-12):
            faces = hull.simplices
            edges = np.unique(np.sort(np.concatenate(
                (faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [0, 2]])), axis=1), axis=0)
            candidates.append(-sites)
    elif rank == 2:
        hull = ConvexHull(centered @ basis[:2].T)
        normal = np.cross(basis[0], basis[1])
        candidates.extend((np.array([normal, -normal]), -sites))
        edges = hull.simplices
    else:
        candidates.append(-sites)
        if n == 2:
            edges = np.array([[0, 1]])
    if len(edges):
        mid = -sites[edges].sum(axis=1)
        norms = np.linalg.norm(mid, axis=1)
        candidates.append(mid[norms > 1e-12] / norms[norms > 1e-12, None])
    if search_region == "mercator":
        # On each latitude boundary, a maximum occurs at a stationary
        # distance to one site or where two neighboring sites tie.
        r = np.sqrt(1-limit**2)
        lon = np.arctan2(sites[:, 1], sites[:, 0]) + np.pi
        for z in (-limit, limit):
            candidates.append(np.column_stack(
                (r*np.cos(lon), r*np.sin(lon), np.full(n, z))))
            if len(edges):
                d = sites[edges[:, 0]] - sites[edges[:, 1]]
                a = r*np.hypot(d[:, 0], d[:, 1])
                ok = (a > 1e-14) & (np.abs(z*d[:, 2]) <= a + 1e-14)
                d, a = d[ok], a[ok]
                phase = np.arctan2(d[:, 1], d[:, 0])
                delta = np.arccos(np.clip(-z*d[:, 2]/a, -1, 1))
                t = np.r_[phase+delta, phase-delta]
                candidates.append(np.column_stack(
                    (r*np.cos(t), r*np.sin(t), np.full(len(t), z))))
    xyz = np.unique(np.round(np.concatenate(candidates), 12), axis=0)
    xyz /= np.linalg.norm(xyz, axis=1)[:, None]
    xyz = xyz[np.abs(xyz[:, 2]) <= limit + 1e-12]
    chord, _ = cKDTree(sites).query(xyz, workers=-1)
    if accuracy < 0:
        raise ValueError('accuracy must be nonnegative')
    if accuracy == 0:
        keep = chord >= chord.max() - 1e-12
    else:
        km = 2 * EARTH_RADIUS * np.arcsin(np.clip(chord / 2, 0, 1))
        keep = km >= km.max() - accuracy - 1e-8
    x, y, z = xyz[keep].T
    return np.degrees(np.column_stack((np.arctan2(z, np.hypot(x, y)), np.arctan2(y, x))))


STICKERS = "Offosch által lerakott matricák.csv"
SAVED = "Far far away.csv"

NUMBER = r'[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?'
POINT = re.compile(rf'POINT\s*\(\s*({NUMBER})\s+({NUMBER})\s*\)', re.I)


def read_saved(path):
    points = []
    with open(path, encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames or 'WKT' not in reader.fieldnames:
            raise ValueError('Missing WKT column')
        for row in reader:
            wkt = (row.get('WKT') or '').strip()
            if not wkt:
                continue
            m = POINT.fullmatch(wkt)
            if not m:
                raise ValueError(f'Invalid WKT: {wkt}')
            lon, lat = m.groups()
            points.append((lat, lon))
    return points


def matches(a, b):
    return Counter(map(tuple, a)) == Counter(map(tuple, b))


def compare_farthest(calculated):
    if not len(calculated):
        raise ValueError('Solver returned no coordinates')
    calculated = [(str(lat), str(lon)) for lat, lon in calculated.tolist()]
    saved = read_saved(SAVED)
    same = matches(calculated, saved)
    print('Coordinates match' if same else 'My Maps coordinates need updating')
    Path('farthest_status.txt').write_text('match' if same else 'different')

    def lines(points):
        return '\n'.join(f'{lat}, {lon}' for lat, lon in sorted(points)) or '(none)'
    body = f'Update the farthest-point layer in Google My Maps manually.\n\nComparison: exact coordinate strings (order-independent).\n\nCalculated ({len(calculated)}), latitude, longitude:\n```text\n{lines(calculated)}\n```\n\nSaved ({len(saved)}):\n```text\n{lines(saved)}\n```\n'
    if len(body) > 60000:
        body = body[:59000] + \
            '\n```\nFull coordinates are in the workflow artifact.\n'
    Path('farthest_issue.md').write_text(body, encoding='utf-8')
    with open('calculated_farthest.csv', 'w', encoding='utf-8', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['latitude', 'longitude'])
        writer.writerows(calculated)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--compare", action="store_true",
                        help="Compare with My Maps and generate notification files")
    args = parser.parse_args()
    points = find_farthest(read_coordinates(STICKERS))
    print("Farthest point list:")
    for point in points:
        print(point.tolist())
    if args.compare:
        compare_farthest(points)


if __name__ == "__main__":
    main()
