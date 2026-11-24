const MS_PER_S = 1000;

function two_digits(value: number): string {
  return String(value).padStart(2, "0");
}

/**
 * game_id = time the game entered ready, YYYYMMDD-HHMMSS (D4).
 * ASSUMPTION: local time of the laptop, as the example 20261103-140500 suggests.
 */
export function make_game_id(now_s: number): string {
  const t = new Date(now_s * MS_PER_S);
  const date = `${t.getFullYear()}${two_digits(t.getMonth() + 1)}${two_digits(t.getDate())}`;
  const time = `${two_digits(t.getHours())}${two_digits(t.getMinutes())}${two_digits(t.getSeconds())}`;
  return `${date}-${time}`;
}
