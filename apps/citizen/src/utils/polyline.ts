/**
 * Polyline encoder and decoder utility for Valhalla routing geometries.
 * Valhalla outputs precision 6 polylines by default.
 * Output coordinates follow GeoJSON standard: [longitude, latitude].
 */

import type { LatLon } from "../types";

/**
 * Decodes a polyline string into an array of [lon, lat] coordinates.
 * Supports standard precision (5) and Valhalla precision (6).
 */
export function decodePolyline(encoded: string, precision: number = 6): Array<[number, number]> {
  if (!encoded || typeof encoded !== "string") {
    return [];
  }

  const coordinates: Array<[number, number]> = [];
  let index = 0;
  let lat = 0;
  let lon = 0;
  const factor = Math.pow(10, precision);

  while (index < encoded.length) {
    let b: number;
    let shift = 0;
    let result = 0;

    do {
      b = encoded.charCodeAt(index++) - 63;
      result |= (b & 0x1f) << shift;
      shift += 5;
    } while (b >= 0x20 && index < encoded.length);

    const dlat = (result & 1) !== 0 ? ~(result >> 1) : result >> 1;
    lat += dlat;

    shift = 0;
    result = 0;

    do {
      b = encoded.charCodeAt(index++) - 63;
      result |= (b & 0x1f) << shift;
      shift += 5;
    } while (b >= 0x20 && index < encoded.length);

    const dlon = (result & 1) !== 0 ? ~(result >> 1) : result >> 1;
    lon += dlon;

    coordinates.push([lon / factor, lat / factor]);
  }

  return coordinates;
}

/**
 * Encodes an array of [lon, lat] coordinates into a polyline string.
 */
export function encodePolyline(
  coordinates: Array<[number, number]>,
  precision: number = 6
): string {
  if (!coordinates || coordinates.length === 0) {
    return "";
  }

  const factor = Math.pow(10, precision);
  let output = "";
  let prevLat = 0;
  let prevLon = 0;

  const encodeValue = (val: number): string => {
    let num = val < 0 ? ~(val << 1) : val << 1;
    let str = "";
    while (num >= 0x20) {
      str += String.fromCharCode((0x20 | (num & 0x1f)) + 63);
      num >>= 5;
    }
    str += String.fromCharCode(num + 63);
    return str;
  };

  for (const [lon, lat] of coordinates) {
    const latScaled = Math.round(lat * factor);
    const lonScaled = Math.round(lon * factor);

    output += encodeValue(latScaled - prevLat);
    output += encodeValue(lonScaled - prevLon);

    prevLat = latScaled;
    prevLon = lonScaled;
  }

  return output;
}

/**
 * Calculates bounding box [[minLon, minLat], [maxLon, maxLat]] for a coordinate array.
 */
export function calculateBounds(
  coordinates: Array<[number, number]>
): [[number, number], [number, number]] | null {
  if (!coordinates || coordinates.length === 0) {
    return null;
  }

  let minLon = coordinates[0][0];
  let maxLon = coordinates[0][0];
  let minLat = coordinates[0][1];
  let maxLat = coordinates[0][1];

  for (let i = 1; i < coordinates.length; i++) {
    const [lon, lat] = coordinates[i];
    if (lon < minLon) minLon = lon;
    if (lon > maxLon) maxLon = lon;
    if (lat < minLat) minLat = lat;
    if (lat > maxLat) maxLat = lat;
  }

  return [
    [minLon, minLat],
    [maxLon, maxLat],
  ];
}

/**
 * Samples a position along a polyline based on a fractional progress (0.0 to 1.0).
 * Returns [longitude, latitude].
 */
export function sampleCoordinateAlongLine(
  coordinates: Array<[number, number]>,
  progress: number
): [number, number] | null {
  if (!coordinates || coordinates.length === 0) {
    return null;
  }
  if (coordinates.length === 1 || progress <= 0) {
    return coordinates[0];
  }
  if (progress >= 1) {
    return coordinates[coordinates.length - 1];
  }

  // Calculate total Euclidean distance as approximation
  const segmentLengths: number[] = [];
  let totalLength = 0;

  for (let i = 0; i < coordinates.length - 1; i++) {
    const [lon1, lat1] = coordinates[i];
    const [lon2, lat2] = coordinates[i + 1];
    const dLon = lon2 - lon1;
    const dLat = lat2 - lat1;
    const len = Math.sqrt(dLon * dLon + dLat * dLat);
    segmentLengths.push(len);
    totalLength += len;
  }

  if (totalLength === 0) {
    return coordinates[0];
  }

  const targetDist = progress * totalLength;
  let accumulated = 0;

  for (let i = 0; i < segmentLengths.length; i++) {
    const segLen = segmentLengths[i];
    if (accumulated + segLen >= targetDist) {
      const segProgress = segLen > 0 ? (targetDist - accumulated) / segLen : 0;
      const [lon1, lat1] = coordinates[i];
      const [lon2, lat2] = coordinates[i + 1];
      const curLon = lon1 + (lon2 - lon1) * segProgress;
      const curLat = lat1 + (lat2 - lat1) * segProgress;
      return [curLon, curLat];
    }
    accumulated += segLen;
  }

  return coordinates[coordinates.length - 1];
}

/**
 * Converts LatLon object to [lon, lat] GeoJSON array.
 */
export function latLonToCoords(point: LatLon): [number, number] {
  return [point.lon, point.lat];
}
