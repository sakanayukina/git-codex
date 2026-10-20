import java.util.Calendar;
import java.util.Scanner;

/**
 * 通用万年历
 * 输入年份，按每行 3 个月打印全年日历。
 */
public class PerpetualCalendar {

    private static final String[] MONTH_NAMES = {
        "１月", "２月", "３月", "４月", "５月", "６月",
        "７月", "８月", "９月", "１０月", "１１月", "１２月"
    };

    // 表头用英文缩写：在任何字体下都能严格对齐（IDEA 控制台也不会歪）
    // 想换回中文，就把下面这行替换成：{"日", "一", "二", "三", "四", "五", "六"}
    private static final String[] WEEK_NAMES = {"Su", "Mo", "Tu", "We", "Th", "Fr", "Sa"};

    // 每个日期占 3 列，一个月 7 天 = 21 列
    private static final int CELL_WIDTH = 3;
    private static final int MONTH_WIDTH = CELL_WIDTH * 7; // 21

    // 月份之间的间隔，想分得更开就改大这个数字
    private static final String GAP = "    "; // 4 个空格

    public static int getDaysOfMonth(int year, int month) {
        Calendar cal = Calendar.getInstance();
        cal.set(year, month - 1, 1); // Calendar 的月份是 0-based
        return cal.getActualMaximum(Calendar.DATE);
    }

    public static int getFirstDayOfWeek(int year, int month) {
        Calendar cal = Calendar.getInstance();
        cal.set(year, month - 1, 1);
        // Calendar.DAY_OF_WEEK: 1=周日 ... 7=周六，减 1 后 0=周日
        return cal.get(Calendar.DAY_OF_WEEK) - 1;
    }

    public static int getMonthHeight(int days, int firstDay) {
        return (days + firstDay + 6) / 7;
    }

    // 计算“显示宽度”：中文/全角字符算 2 列，数字和空格算 1 列
    private static int displayWidth(String s) {
        int width = 0;
        for (int i = 0; i < s.length(); i++) {
            width += (s.charAt(i) >= 0x1100) ? 2 : 1;
        }
        return width;
    }

    // 把字符串居中到指定显示宽度（只用于月份标题）
    private static String center(String s, int width) {
        int left = (width - displayWidth(s)) / 2;
        StringBuilder sb = new StringBuilder();
        for (int i = 0; i < left; i++) {
            sb.append(' ');
        }
        sb.append(s);
        while (displayWidth(sb.toString()) < width) {
            sb.append(' ');
        }
        return sb.toString();
    }

    // 把字符串靠左对齐到指定显示宽度（中文占 2 列）
    private static String padRight(String s, int width) {
        StringBuilder sb = new StringBuilder();
        sb.append(s);
        while (displayWidth(sb.toString()) < width) {
            sb.append(' ');
        }
        return sb.toString();
    }

    // 打印一个月份块，并在后面加上月份之间的间隔
    private static void printMonth(String field) {
        System.out.print(field);
        System.out.print(GAP);
    }

    // 生成某个月第 row 行的日期字符串（每个日期右对齐占 3 列）
    public static String getRowString(int firstDay, int days, int row) {
        StringBuilder sb = new StringBuilder();
        int startDate = row * 7 - firstDay + 1;
        for (int d = startDate; d < startDate + 7; d++) {
            if (d < 1 || d > days) {
                sb.append("   ");                  // 空白占 3 列
            } else {
                sb.append(String.format("%-3d", d)); // 日期左对齐占 3 列
            }
        }
        return sb.toString();
    }

    private static String spaces(int n) {
        StringBuilder sb = new StringBuilder();
        for (int i = 0; i < n; i++) {
            sb.append(' ');
        }
        return sb.toString();
    }

    public static void printYear(int year, int monthsPerRow) {
        int[] daysOfMonth = new int[12];
        int[] firstDayOfMonth = new int[12];
        int[] heightOfMonth = new int[12];

        for (int m = 0; m < 12; m++) {
            daysOfMonth[m] = getDaysOfMonth(year, m + 1);
            firstDayOfMonth[m] = getFirstDayOfWeek(year, m + 1);
            heightOfMonth[m] = getMonthHeight(daysOfMonth[m], firstDayOfMonth[m]);
        }

        // 星期表头：每个中文占 2 列，靠左放进 3 列里，正好 21 列
        StringBuilder header = new StringBuilder();
        for (String name : WEEK_NAMES) {
            header.append(padRight(name, CELL_WIDTH));
        }
        String weekHeader = header.toString();

        int rowGroups = (12 + monthsPerRow - 1) / monthsPerRow;

        for (int group = 0; group < rowGroups; group++) {
            int startMonth = group * monthsPerRow;
            int endMonth = Math.min(startMonth + monthsPerRow - 1, 11);

            // 1) 月份标题
            for (int m = startMonth; m <= endMonth; m++) {
                printMonth(center(MONTH_NAMES[m], MONTH_WIDTH));
            }
            System.out.println();

            // 2) 星期表头
            for (int m = startMonth; m <= endMonth; m++) {
                printMonth(weekHeader);
            }
            System.out.println();

            // 3) 这一组里最高的月份有几行
            int maxHeight = 0;
            for (int m = startMonth; m <= endMonth; m++) {
                maxHeight = Math.max(maxHeight, heightOfMonth[m]);
            }

            // 4) 逐行打印日期
            for (int row = 0; row < maxHeight; row++) {
                for (int m = startMonth; m <= endMonth; m++) {
                    String cell = row < heightOfMonth[m]
                            ? getRowString(firstDayOfMonth[m], daysOfMonth[m], row)
                            : spaces(MONTH_WIDTH);
                    printMonth(cell);
                }
                System.out.println();
            }

            System.out.println(); // 每一大组之间空一行
        }
    }

    public static void main(String[] args) {
        Scanner sc = new Scanner(System.in);
        System.out.print("请输入年份：");
        int year = sc.nextInt();
        System.out.println();
        System.out.println("============ " + year + "年万年历 ============");
        System.out.println();
        printYear(year, 3); // 每行 3 个月
        sc.close();
    }
}
