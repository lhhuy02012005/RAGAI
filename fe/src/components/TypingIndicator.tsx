import { motion } from "framer-motion";

const TypingIndicator = () => (
  <div className="flex gap-1 px-2 py-1 items-center">
    {[0, 1, 2].map((i) => (
      <motion.div
        key={i}
        className="w-1.5 h-1.5 bg-gray-400 rounded-full"
        animate={{ y: [0, -5, 0] }}
        transition={{
          duration: 0.6,
          repeat: Infinity,
          delay: i * 0.2,
        }}
      />
    ))}
  </div>
);

export default TypingIndicator;