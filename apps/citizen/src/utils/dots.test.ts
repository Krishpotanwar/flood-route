import test from "node:test";
import assert from "node:assert/strict";
import { advanceDot } from "./dots.ts";

test("dots repel locally, settle exactly, and stay finite under the pointer", () => {
  const near = { x: 30, y: 30, offsetX: 0, offsetY: 0 };
  assert.equal(advanceDot(near, { x: 20, y: 30 }, 0.16), true);
  assert.ok(near.offsetX > 0 && near.offsetX < 12);
  assert.equal(near.offsetY, 0);
  let moving = true;
  for (let frame = 0; frame < 90; frame++) moving = advanceDot(near, { x: 20, y: 30 }, 0.16);
  assert.equal(moving, false);
  for (let frame = 0; frame < 90; frame++) moving = advanceDot(near, null, 0.16);
  assert.equal(moving, false);
  assert.deepEqual(near, { x: 30, y: 30, offsetX: 0, offsetY: 0 });
  assert.equal(advanceDot(near, { x: 30, y: 30 }, 0.16), false);
  assert.equal(advanceDot(near, { x: 300, y: 300 }, 0.16), false);
});
