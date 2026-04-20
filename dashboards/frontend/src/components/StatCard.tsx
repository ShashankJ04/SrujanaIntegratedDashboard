import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import Typography from "@mui/material/Typography";
import type { SxProps, Theme } from "@mui/material/styles";

interface StatCardProps {
  title: string;
  value: React.ReactNode;
  subtitle?: string;
  sx?: SxProps<Theme>;
}

export default function StatCard({ title, value, subtitle, sx }: StatCardProps) {
  return (
    <Card sx={sx}>
      <CardContent sx={{ py: 1.5, px: 2, "&:last-child": { pb: 1.5 } }}>
        <Typography variant="caption" color="text.secondary" sx={{ textTransform: "uppercase", letterSpacing: "0.08em" }}>
          {title}
        </Typography>
        <Typography variant="h5" sx={{ lineHeight: 1.3 }}>{value}</Typography>
        {subtitle && (
          <Typography variant="body2" color="text.secondary" sx={{ mt: 0.25 }}>
            {subtitle}
          </Typography>
        )}
      </CardContent>
    </Card>
  );
}
