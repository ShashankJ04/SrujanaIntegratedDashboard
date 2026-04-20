import { useEffect, useRef } from "react";
import * as echarts from "echarts";
import type { EChartsOption } from "echarts";
import { useTheme } from "@mui/material/styles";
import Box from "@mui/material/Box";

interface ChartProps {
  option: EChartsOption;
  height?: number | string;
  loading?: boolean;
}

/**
 * Reusable ECharts wrapper component.
 * Pass any ECharts option object and it handles init, resize, and cleanup.
 */
export default function Chart({ option, height = 350, loading = false }: ChartProps) {
  const chartRef = useRef<HTMLDivElement>(null);
  const instanceRef = useRef<echarts.ECharts | null>(null);
  const theme = useTheme();

  useEffect(() => {
    if (!chartRef.current) return;

    instanceRef.current = echarts.init(chartRef.current);

    const handleResize = () => instanceRef.current?.resize();
    window.addEventListener("resize", handleResize);

    return () => {
      window.removeEventListener("resize", handleResize);
      instanceRef.current?.dispose();
    };
  }, []);

  useEffect(() => {
    if (!instanceRef.current) return;

    if (loading) {
      instanceRef.current.showLoading("default", {
        text: "",
        color: theme.palette.primary.main,
      });
    } else {
      instanceRef.current.hideLoading();
      instanceRef.current.setOption(option, true);
    }
  }, [option, loading, theme]);

  return <Box ref={chartRef} sx={{ width: "100%", height }} />;
}
