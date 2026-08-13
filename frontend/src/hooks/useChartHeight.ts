/**
 * 图表自适应高度 Hook
 *
 * 视口高度不足时收缩图表高度避免溢出：取 min(基础高度, 视口高度 - 预留偏移)，
 * 同时保证不低于最小值。监听 resize 实时更新。
 */
import { useEffect, useState } from 'react';

export function useChartHeight(baseHeight = 420, min = 280, offset = 320): number {
  const calc = () =>
    Math.max(min, Math.min(baseHeight, (typeof window !== 'undefined' ? window.innerHeight : 800) - offset));

  const [chartHeight, setChartHeight] = useState(calc);

  useEffect(() => {
    const onResize = () => setChartHeight(calc());
    window.addEventListener('resize', onResize);
    onResize();
    return () => window.removeEventListener('resize', onResize);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [baseHeight, min, offset]);

  return chartHeight;
}
