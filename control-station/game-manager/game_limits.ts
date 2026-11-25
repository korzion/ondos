// Fixed limits GameManager uses, with the place in the design document each one comes from.
// They are not in shared/interfaces/constants.json yet, so they are named here.

/** IF-05: game/state is published at 10 Hz (E-R9). */
export const HEARTBEAT_PERIOD_MS = 100;

/** IF-02 platform/state, reader "Control Station game management": 200 ms (sections 5.3, 5.4). */
export const PLATFORM_STATE_MAX_AGE_MS = 200;

/** IF-04 vision/ball, reader "Control Station game management": 200 ms (section 5.3 resume rule). */
export const BALL_MAX_AGE_MS = 200;

/** IF-04 plan/route, reader "E GameManager": 300 ms (section 5.3 resume rule). */
export const ROUTE_MAX_AGE_MS = 300;

/** IF-04 vision/edit_state, reader "E GameManager": 2 s (section 5.3 resume rule). */
export const EDIT_STATE_MAX_AGE_MS = 2000;

/**
 * IF-02 glove/state gives 200 ms only for the Control Station reader; GameManager uses the same limit
 * to decide whether the glove is connected.
 */
export const GLOVE_STATE_MAX_AGE_MS = 200;

/** How long main.ts waits for the retained game/state of a previous run (section 5.4). */
export const RETAINED_STATE_WAIT_MS = 500;
