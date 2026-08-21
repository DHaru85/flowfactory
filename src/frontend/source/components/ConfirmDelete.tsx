import { Button, Popconfirm, message } from "antd";
import type { ReactElement } from "react";

import { errorMessage } from "@/api/client";

interface Props {
  disabled?: boolean;
  onConfirm: () => Promise<void>;
}

export function ConfirmDelete({ disabled, onConfirm }: Props): ReactElement {
  return (
    <Popconfirm
      title="确认删除该数据？此操作不可从列表恢复。"
      okText="删除"
      cancelText="取消"
      disabled={disabled}
      onConfirm={() =>
        onConfirm().catch((err: unknown) => {
          message.error(errorMessage(err, "删除失败"));
        })
      }
    >
      <Button
        type="link"
        danger
        disabled={disabled}
        onClick={(event) => event.stopPropagation()}
      >
        删除
      </Button>
    </Popconfirm>
  );
}
